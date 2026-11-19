import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fwlib.py')
s = open(p, encoding='utf-8').read()
pairs = [
("""            # convert to physical guided-mode amplitude a: b+ = (a/2)*N*dy*e^{i beta x}
            aplus = 2.0 * abs(bplus) / (nwin * dy)
            aminus = 2.0 * abs(bminus) / (nwin * dy)""",
"""            # physical guided-mode (phasor) amplitude: b+ = a*N/4 with the Hann window
            aplus = 4.0 * abs(bplus) / nwin
            aminus = 4.0 * abs(bminus) / nwin"""),
("""            integ = np.sum(np.imag(C[ilocal] * D))
            return float(2.0 * om / nwin ** 2 * self.dx * integ)""",
"""            integ = np.sum(np.imag(np.conj(C[ilocal]) * D))
            return float(4.0 * 2.0 * om / nwin ** 2 * self.dx * integ)"""),
("""            integ = np.sum(np.imag(C[:, ilocal] * D))
            return float(2.0 * om / nwin ** 2 * self.dx * integ)""",
"""            integ = np.sum(np.imag(np.conj(C[:, ilocal]) * D))
            return float(4.0 * 2.0 * om / nwin ** 2 * self.dx * integ)"""),
("""        psi, Dn = self._sample_line(C, fp)
        integ = np.sum(np.imag(np.conj(psi) * Dn))
        return float(2.0 * om / nwin ** 2 * fp['dl'] * integ)""",
"""        psi, Dn = self._sample_line(C, fp)
        integ = np.sum(np.imag(np.conj(psi) * Dn))
        return float(4.0 * 2.0 * om / nwin ** 2 * fp['dl'] * integ)"""),
("""            inners.append(dl * np.sum(phi * psi))
            innerDs.append(dl * np.sum(phi * Dn))
            fluxes.append((2 * om / N ** 2) * dl * np.sum(np.imag(np.conj(psi) * Dn)))""",
"""            inners.append(dl * np.sum(phi * psi))
            innerDs.append(dl * np.sum(phi * Dn))
            fluxes.append(4.0 * (2 * om / N ** 2) * dl * np.sum(np.imag(np.conj(psi) * Dn)))"""),
("""        aplus = 2.0 * np.abs(bplus) / N
        aminus = 2.0 * np.abs(bminus) / N""",
"""        aplus = 4.0 * np.abs(bplus) / N
        aminus = 4.0 * np.abs(bminus) / N"""),
]
for old, new in pairs:
    if old not in s:
        print('WARNING pattern not found:', old[:60])
    s = s.replace(old, new)
open(p, 'w', encoding='utf-8').write(s)
print('patched fwlib normalization')
