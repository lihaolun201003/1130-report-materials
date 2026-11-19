"""Patch fwlib3d: robust 3-D port mode via EIM profile + Rayleigh quotient.

The exact 2-D transverse eigenproblem (eigsh) is ill-conditioned for the square
channel because the discrete box modes form a dense cluster around the guided
eigenvalue.  The guided mode is instead approximated by the separable EIM profile
(accurate to 3e-5 in n_eff) and its discrete eigenvalue is obtained from the
Rayleigh quotient of the discretised operator; the port decomposition is then
exact for the numerical guided mode because the forward/backward splitting only
requires the *derivative* eigenvalue beta_d and the same profile in both terms.
"""
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fwlib3d.py')
s = open(p, encoding='utf-8').read()

old = """    # ----------------------------------------------------------------- modes
    def channel_mode(self, yc, zc, w=W_CORE, h=W_CORE, transpose=False):
        \"\"\"discrete mode of an isolated axis-aligned channel; returns phi (2-D
        array on the transverse grid), s, beta, beta_d, n_eff.\"\"\"
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
"""
new = """    # ----------------------------------------------------------------- modes
    def _eim_profiles(self, w, h, transpose=False):
        \"\"\"separable EIM profiles (1-D slab modes) for the isolated channel.\"\"\"
        g = self.g
        if not transpose:
            ax1, ax2 = g.axes[1], g.axes[2]
        else:
            ax1, ax2 = g.axes[0], g.axes[2]
        sol1 = fw.slab_analytic(g.n_core, g.n_clad, w)          # first stage
        sol2 = fw.slab_analytic(sol1['neff'], g.n_clad, h)      # second stage
        p1 = fw.slab_profile(ax1, sol1)
        p2 = fw.slab_profile(ax2, sol2)
        return p1, p2, sol1, sol2

    def _rayleigh_s(self, phi, npro):
        \"\"\"discrete eigenvalue s = <phi|L + (w_eff/c)^2 n^2|phi>/<phi|phi>
        for the given (smooth) trial profile, 2-D separable stencil.\"\"\"
        c = fw.fd2_coeffs(self.g.order)
        m = len(c) - 1
        lap = c[0] * phi
        for ax in range(2):
            for k in range(1, m + 1):
                sa = [slice(None)] * 2
                sb = [slice(None)] * 2
                sa[ax] = slice(k, None); sb[ax] = slice(None, -k)
                lap[tuple(sa)] += c[k] * phi[tuple(sb)]
                sa[ax] = slice(None, -k); sb[ax] = slice(k, None)
                lap[tuple(sa)] += c[k] * phi[tuple(sb)]
        lap /= self.dx ** 2
        num = np.sum(phi * (lap + (self.g.omega_eff / fw.C0) ** 2 * npro ** 2 * phi))
        den = np.sum(phi * phi)
        return num / den

    def channel_mode(self, yc, zc, w=W_CORE, h=W_CORE, transpose=False):
        \"\"\"isolated axis-aligned channel mode: returns phi (2-D array on the
        transverse grid, normalised to int phi^2 dA = 1), s, beta, beta_d, n_eff.
        Uses the EIM profile + discrete Rayleigh quotient (robust).\"\"\"
        g = self.g
        if not transpose:
            ax1, ax2 = g.axes[1], g.axes[2]
        else:
            ax1, ax2 = g.axes[0], g.axes[2]
        npro = channel_section(ax1, ax2, yc, zc, w, h, g.n_core, g.n_clad)
        p1, p2, sol1, sol2 = self._eim_profiles(w, h, transpose)
        phi = p1[:, None] * p2[None, :]
        phi = phi / np.sqrt(np.sum(phi ** 2) * self.dx ** 2)
        s = self._rayleigh_s(phi, npro)
        beta = fw.beta_from_stencil_eig(s, self.dx, g.order)
        bd = fw.beta_deriv_fd(beta, self.dx, g.order)
        return phi, s, beta, bd, beta / K0
"""
assert old in s
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(s)
print('patched fwlib3d channel_mode (EIM + Rayleigh quotient)')
