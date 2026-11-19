"""3-D scalar FDTD layer: ports, sources, probes and the run loop for
psi_tt = (c/n(x,y,z))^2 lap(psi) on the 6th-order stencil.

The heavy lifting (leapfrog update, separable 6th-order Laplacian via conv2d,
graded absorber) is in fwlib.Stepper; this module adds the 3-D measurement
machinery (modal planes, boundary flux, energy budget).

Grid conventions: fields are stored with a zero-padded border of m = order//2
cells on every side and an extra y-pad of m rows on each side (needed by the
separable conv2d Laplacian).  Index helper: flat(i, j, k) maps (x index,
transverse index j, z index) to the flat storage index.
"""
import json
import os
import time

import numpy as np
import torch

import fwlib as fw

C0 = fw.C0
K0 = fw.K0
N_CORE = fw.N_CORE
N_CLAD = fw.N_CLAD
W_CORE = fw.W_CORE
NEFF3D = fw.NEFF3D_TARGET if hasattr(fw, 'NEFF3D_TARGET') else 1.504557


def channel_section(ax1, ax2, c1, c2, w, h, n_core=N_CORE, n_clad=N_CLAD):
    """area-averaged index cross-section of an axis-aligned rectangular channel
    centred at (c1,c2) with width w (axis1) and height h (axis2)."""
    dx = ax1[1] - ax1[0]
    fy = np.clip((w / 2 - np.abs(ax1 - c1) + dx / 2) / dx, 0.0, 1.0)
    fz = np.clip((h / 2 - np.abs(ax2 - c2) + dx / 2) / dx, 0.0, 1.0)
    n2 = n_clad ** 2 + (n_core ** 2 - n_clad ** 2) * fy[:, None] * fz[None, :]
    return np.sqrt(n2)


class Sim3D:
    def __init__(self, phys, t_abs, dx, order=6, guides=None,
                 n_core=N_CORE, n_clad=N_CLAD, A_abs=7.0, m_abs=3.0,
                 device='cuda', label='sim3d', S_factor=0.90):
        self.label = label
        self.g = fw.Grid(phys, t_abs, dx, order, n_core=n_core, n_clad=n_clad,
                         A_abs=A_abs, m_abs=m_abs, S_factor=S_factor)
        self.g.build_index(guides if guides is not None else [])
        self.g.build_sigma()
        self.st = fw.Stepper(self.g, device=device)
        self.device = self.st.device
        self.m = order // 2
        self.N = list(self.g.N)
        self.Nyp = self.st.Ny_pad
        self.dx = dx
        self.dt = self.g.dt
        self.omega = fw.OMEGA0
        self.T = 2 * np.pi / fw.OMEGA0
        self.vg = C0 / NEFF3D
        self.ports = []
        self.probes = {}
        self.source = None
        self.t_ramp = 0.0
        self.proj = None

    # ------------------------------------------------------------- indexing
    def idx_x(self, x):
        return int(round((x - self.g.axes[0][0]) / self.dx))

    def idx_y(self, y):
        return int(round((y - self.g.axes[1][0]) / self.dx))

    def idx_z(self, z):
        return int(round((z - self.g.axes[2][0]) / self.dx))

    def flat(self, i, j, k):
        """flat index into the (Nx,Nyp,Nz) field array; j is the *transverse*
        index (0..Ny-1) without the y-pad offset."""
        return i * self.Nyp * self.N[2] + (j + self.m) * self.N[2] + k

    # ----------------------------------------------------------------- modes
    def channel_mode(self, yc, zc, w=W_CORE, h=W_CORE, transpose=False):
        """discrete mode of an isolated axis-aligned channel; returns phi (2-D
        array on the transverse grid), s, beta, beta_d, n_eff."""
        g = self.g
        if not transpose:
            ax1, ax2 = g.axes[1], g.axes[2]
        else:
            ax1, ax2 = g.axes[0], g.axes[2]
        npro = channel_section(ax1, ax2, yc, zc, w, h, g.n_core, g.n_clad)
        s, phi = fw.discrete_mode_2d((ax1, ax2), npro, self.dx, g.order, g.omega_eff)
        beta = fw.beta_from_stencil_eig(s, self.dx, g.order)
        bd = fw.beta_deriv_fd(beta, self.dx, g.order)
        return phi, s, beta, bd, beta / K0

    # ----------------------------------------------------------------- ports
    def add_port_x(self, x, yc, zc, name, w=W_CORE, h=W_CORE):
        """modal port on a plane x=const; mode centred at (yc,zc)."""
        ix = self.idx_x(x)
        phi, s, beta, bd, neff = self.channel_mode(yc, zc, w, h)
        phi_pad = np.zeros((self.Nyp, self.N[2]))
        phi_pad[self.m:self.m + phi.shape[0], :] = phi
        m = self.m
        sl = (slice(ix - m - 1, ix + m + 1 + 1), slice(0, self.Nyp), slice(0, self.N[2]))
        shape = (2 * m + 3, self.Nyp, self.N[2])
        box = fw.DftBox(sl, shape, self.device)
        self.ports.append(dict(name=name, kind='x', ix=ix, box=box, phi=phi_pad,
                               beta=beta, beta_d=bd, neff=neff, pos=(x, yc, zc)))
        return self.ports[-1]

    def add_port_y(self, y, xc, zc, name, w=W_CORE, h=W_CORE):
        iy = self.idx_y(y)
        phi, s, beta, bd, neff = self.channel_mode(xc, zc, w, h, transpose=True)
        # phi is on (x, z) grid; keep as is
        m = self.m
        sl = (slice(0, self.N[0]), slice(iy - m, iy + m + 1), slice(0, self.N[2]))
        shape = (self.N[0], 2 * m + 1, self.N[2])
        box = fw.DftBox(sl, shape, self.device)
        self.ports.append(dict(name=name, kind='y', iy=iy, box=box, phi=phi,
                               beta=beta, beta_d=bd, neff=neff, pos=(xc, y, zc)))
        return self.ports[-1]

    def add_boundary_probes(self, name='bnd'):
        g = self.g
        m = g.pad
        i0p, i1p = g.i_phys[0]
        j0p, j1p = g.i_phys[1]
        k0p, k1p = g.i_phys[2]
        Nx, Ny, Nz = self.N
        Nyp = self.Nyp
        self.probes[name + '_L'] = fw.DftBox(
            (slice(i0p - m, i0p + m + 1), slice(0, Nyp), slice(0, Nz)),
            (2 * m + 1, Nyp, Nz), self.device)
        self.probes[name + '_R'] = fw.DftBox(
            (slice(i1p - m, i1p + m + 1), slice(0, Nyp), slice(0, Nz)),
            (2 * m + 1, Nyp, Nz), self.device)
        self.probes[name + '_B'] = fw.DftBox(
            (slice(0, Nx), slice(m + j0p - m, m + j0p + m + 1), slice(0, Nz)),
            (Nx, 2 * m + 1, Nz), self.device)
        self.probes[name + '_T'] = fw.DftBox(
            (slice(0, Nx), slice(m + j1p - m, m + j1p + m + 1), slice(0, Nz)),
            (Nx, 2 * m + 1, Nz), self.device)
        self.probes[name + '_Bz'] = fw.DftBox(
            (slice(0, Nx), slice(0, Nyp), slice(k0p - m, k0p + m + 1)),
            (Nx, Nyp, 2 * m + 1), self.device)
        self.probes[name + '_Tz'] = fw.DftBox(
            (slice(0, Nx), slice(0, Nyp), slice(k1p - m, k1p + m + 1)),
            (Nx, Nyp, 2 * m + 1), self.device)

    def add_beta_projector(self, x0, x1, yc, zc, name='proj', w=W_CORE, h=W_CORE):
        phi, s, beta, bd, neff = self.channel_mode(yc, zc, w, h)
        i0, i1 = self.idx_x(x0), self.idx_x(x1) + 1
        phi_pad = np.zeros((self.Nyp, self.N[2]))
        phi_pad[self.m:self.m + phi.shape[0], :] = phi
        self.proj = dict(i0=i0, i1=i1, phi=phi_pad, beta=beta, beta_d=bd,
                         neff=neff,
                         re=torch.zeros(i1 - i0, device=self.device, dtype=torch.float32),
                         im=torch.zeros(i1 - i0, device=self.device, dtype=torch.float32))

    # ---------------------------------------------------------------- source
    def set_source(self, x, yc, zc, amp=None, w=W_CORE, h=W_CORE,
                   ramp_periods=10.0):
        ix = self.idx_x(x)
        phi, s, beta, bd, neff = self.channel_mode(yc, zc, w, h)
        m = self.m
        jj, kk = np.meshgrid(np.arange(phi.shape[0]), np.arange(phi.shape[1]),
                             indexing='ij')
        idx = self.flat(ix, jj.ravel(), kk.ravel())
        vals = phi.ravel().astype(np.float32)
        if amp is None:
            v2 = (C0 / neff) ** 2
            amp = 2.0 * beta * v2 * 1e3
        self.source = dict(x=x, ix=ix, idx=torch.as_tensor(idx.astype(np.int64),
                                                          device=self.device),
                           vals=torch.as_tensor(vals, device=self.device,
                                                dtype=torch.float32),
                           amp=float(amp), pos=(yc, zc), beta=beta)
        self.t_ramp = ramp_periods * self.T
        return self.source

    # --------------------------------------------------------------- run loop
    def run(self, t_settle_extra=0.25e-12, window_periods=60.0, print_every=2000,
            max_steps=200000):
        g, st = self.g, self.st
        src = self.source
        pts = [(float(src['x']), float(src['pos'][0]), float(src['pos'][1]))]
        for p in self.ports:
            pts.append(p['pos'])
        for nm, bx in self.probes.items():
            i0 = bx.sl[0].start; i1 = bx.sl[0].stop
            j0 = bx.sl[1].start; j1 = bx.sl[1].stop
            k0 = bx.sl[2].start; k1 = bx.sl[2].stop
            pts.append((g.axes[0][i0], g.axes[1][max(0, j0 - self.m)],
                        g.axes[2][k0]))
            pts.append((g.axes[0][i1 - 1], g.axes[1][min(g.N[1] - 1, j1 - 1 - self.m)],
                        g.axes[2][k1 - 1]))
        x0s = float(src['x']); y0s, z0s = src['pos'][0], src['pos'][1]
        dmax = max([np.sqrt((a - x0s) ** 2 + (b - y0s) ** 2 + (c - z0s) ** 2)
                    for (a, b, c) in pts] + [0.0])
        t_settle = self.t_ramp + dmax / self.vg + t_settle_extra
        t_win = window_periods * self.T
        n_start = int(np.ceil(t_settle / self.dt))
        n_win = int(np.round(t_win / self.dt))
        n_tot = min(n_start + n_win, max_steps)
        self.meta = dict(t_ramp=self.t_ramp, t_settle=t_settle, t_window=t_win,
                         n_start=n_start, n_win=n_win, n_tot=n_tot, dmax=dmax,
                         dt=self.dt, dx=self.dx, order=g.order, N=list(g.N),
                         Nyp=self.Nyp, cells=int(self.N[0] * self.N[1] * self.N[2]),
                         S=g.S, S_max=g.S_max, t_abs=g.t_abs)
        t = np.arange(n_tot + 1) * self.dt
        tr = np.minimum(t, self.t_ramp)
        ramp = np.where(t < self.t_ramp,
                        0.5 * (1.0 - np.cos(np.pi * tr / max(self.t_ramp, 1e-30))),
                        1.0)
        src_ts = (src['amp'] * ramp * np.sin(self.omega * t) * self.dt * self.dt
                  ).astype(np.float64)
        st.psi_a.zero_(); st.psi_b.zero_(); st.psi_c.zero_()
        st.steps_done = 0
        win_len = max(n_win, 1)
        z = complex(1.0, 0.0)
        dphase = np.exp(1j * self.omega * self.dt)
        kk = 0
        t0 = time.time()
        phi_proj = None
        if self.proj is not None:
            phi_proj = torch.as_tensor(self.proj['phi'], device=self.device,
                                       dtype=torch.float32)
        for n in range(n_tot):
            st.step(source=(src['idx'], src['vals'], float(src_ts[n])))
            if n >= n_start:
                w = 0.5 * (1.0 - np.cos(2 * np.pi * kk / win_len))
                zr, zi = z.real * w, z.imag * w
                z *= dphase
                kk += 1
                for bx in self.probes.values():
                    bx.add(st.psi_a, zr, zi, 1.0)
                for p in self.ports:
                    p['box'].add(st.psi_a, zr, zi, 1.0)
                if self.proj is not None:
                    pr = self.proj
                    sub = st.psi_a[pr['i0']:pr['i1']]
                    prod = (sub * phi_proj).sum(dim=(1, 2))
                    pr['re'].add_(prod, alpha=zr)
                    pr['im'].add_(prod, alpha=zi)
            if (n + 1) % print_every == 0:
                mx = float(st.psi_a.abs().max().item())
                el = time.time() - t0
                print('  [%s] step %d/%d max|psi|=%.3e %.1fs (%.0f steps/s)'
                      % (self.label, n + 1, n_tot, mx, el, (n + 1) / el), flush=True)
                if not np.isfinite(mx) or mx > 1e6:
                    raise RuntimeError('divergence')
        self.wall = time.time() - t0
        self.n_tot = n_tot
        self.window_values = kk
        print('  [%s] done %d steps in %.1fs' % (self.label, n_tot, self.wall),
              flush=True)
        return self

    # ------------------------------------------------------------- analysis
    def _d1(self, C, ilocal, axis_local):
        """discrete first derivative along axis_local at local index ilocal."""
        d = fw.fd1_coeffs(self.g.order)
        out = np.zeros_like(np.take(C, ilocal, axis=axis_local))
        for k, dk in enumerate(d, start=1):
            ip = [slice(None)] * C.ndim
            im = [slice(None)] * C.ndim
            ip[axis_local] = ilocal + k
            im[axis_local] = ilocal - k
            out += dk * (C[tuple(ip)] - C[tuple(im)]) / self.dx
        return out

    def _flux(self, C, ilocal, axis_local):
        om = self.omega
        N = self.window_values
        d = fw.fd1_coeffs(self.g.order)
        out = np.zeros_like(np.take(C, ilocal, axis=axis_local))
        for k, dk in enumerate(d, start=1):
            ip = [slice(None)] * C.ndim
            im = [slice(None)] * C.ndim
            ip[axis_local] = ilocal + k
            im[axis_local] = ilocal - k
            out += dk * (C[tuple(ip)] - C[tuple(im)]) / self.dx
        integ = np.sum(np.imag(np.conj(np.take(C, ilocal, axis=axis_local)) * out))
        vol = self.dx ** (C.ndim - 1)
        return float(4.0 * 2.0 * om / N ** 2 * vol * integ)

    def analyse(self):
        res = dict(ports={}, boundary={})
        dyz = self.dx * self.dx
        for p in self.ports:
            C = p['box'].get()
            m = self.m
            if p['kind'] == 'x':
                il = p['ix'] - p['box'].sl[0].start
                psi = C[il]
                D = self._d1(C, il, 0)
                phi = p['phi']
                inner = dyz * np.sum(phi * psi)
                innerD = dyz * np.sum(phi * D)
                Pf = self._flux(C, il, 0)
            else:
                il = p['iy'] - p['box'].sl[1].start
                psi = C[:, il, :]
                D = self._d1(C, il, 1)
                phi = p['phi']
                inner = dyz * np.sum(phi * psi)
                innerD = dyz * np.sum(phi * D)
                Pf = self._flux(C, il, 1)
            bd = p['beta_d']
            bplus = 0.5 * (inner + innerD / (1j * bd))
            bminus = 0.5 * (inner - innerD / (1j * bd))
            aplus = 4.0 * abs(bplus) / self.window_values
            aminus = 4.0 * abs(bminus) / self.window_values
            res['ports'][p['name']] = dict(
                a_plus=float(aplus), a_minus=float(aminus),
                ratio_db=float(20 * np.log10(max(aminus / max(aplus, 1e-300), 1e-30))),
                P_plus=float(0.5 * self.omega * p['beta'] * aplus ** 2),
                P_minus=float(0.5 * self.omega * p['beta'] * aminus ** 2),
                P_flux=float(Pf), beta=float(p['beta']), neff=float(p['neff']))
        for nm, bx in self.probes.items():
            C = bx.get()
            m = self.m
            if nm.endswith('_L'):
                Pf = -self._flux(C, m, 0)
            elif nm.endswith('_R'):
                Pf = self._flux(C, m, 0)
            elif nm.endswith('_B'):
                Pf = -self._flux(C, m, 1)
            elif nm.endswith('_T'):
                Pf = self._flux(C, m, 1)
            elif nm.endswith('_Bz'):
                Pf = -self._flux(C, m, 2)
            elif nm.endswith('_Tz'):
                Pf = self._flux(C, m, 2)
            else:
                continue
            res['boundary'][nm] = float(Pf)
        return res

    def beta_from_projector(self):
        pr = self.proj
        c = pr['re'].detach().cpu().numpy() + 1j * pr['im'].detach().cpu().numpy()
        ph = np.unwrap(np.angle(c))
        x = self.g.axes[0][pr['i0']:pr['i1']]
        A = np.vstack([x, np.ones_like(x)]).T
        coef, *_ = np.linalg.lstsq(A, ph, rcond=None)
        return dict(beta=float(coef[0]), neff=float(coef[0] / K0),
                    beta_discrete=pr['beta'], neff_discrete=pr['beta'] / K0,
                    resid=float(np.std(ph - A @ coef)))
