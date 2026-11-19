import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fwlib.py')
s = open(p, encoding='utf-8').read()

anchor = """        self.t_ramp = ramp_periods * self.T
        return self.source
"""
new = """        self.t_ramp = ramp_periods * self.T
        return self.source

    def set_source_oblique(self, center, theta, u0, amp=None, w=W_SLAB,
                           ramp_periods=10.0, band=0.75, phi_norm=400.0):
        \"\"\"soft mode-shaped line source perpendicular to a straight arm with
        direction angle theta, located at u=u0 along the arm from `center`.
        The source profile is the analytic slab mode sampled at the cells that
        intersect the source line.\"\"\"
        g = self.g
        eu = np.array([np.cos(theta), np.sin(theta)])
        es = np.array([-np.sin(theta), np.cos(theta)])
        cpt = np.array(center, dtype=np.float64) + u0 * eu
        X = g.axes[0][:, None]
        Y = g.axes[1][None, :]
        u = (X - cpt[0]) * eu[0] + (Y - cpt[1]) * eu[1]
        s = (X - cpt[0]) * es[0] + (Y - cpt[1]) * es[1]
        mask = (np.abs(u) <= band * self.dx) & (np.abs(s) <= w / 2.0)
        idx = np.flatnonzero(mask.ravel())
        sol = fw_slab_analytic(w=w)
        vals = fw_slab_profile(np.asarray(s[mask], dtype=np.float64), sol)
        vals = vals / np.max(np.abs(vals))
        idx_t = torch.as_tensor(idx.astype(np.int64), device=self.device,
                                dtype=torch.long)
        vals_t = torch.as_tensor(vals.astype(np.float32), device=self.device,
                                 dtype=self.dtype)
        if amp is None:
            v2 = (C0 / sol['neff']) ** 2
            amp = 2.0 * sol['beta'] * v2 / phi_norm
        self.source = dict(x=float(cpt[0]), y=float(cpt[1]), ix=-1, idx=idx_t,
                           vals=vals_t, amp=float(amp), theta=theta, u0=u0)
        self.t_ramp = ramp_periods * self.T
        return self.source
"""
assert anchor in s
s = s.replace(anchor, new, 1)
open(p, 'w', encoding='utf-8').write(s)
print('added set_source_oblique')
