# Apple TV pe LG, în România

Ai Apple TV instalat pe LG, dar apare „Apple TV is not available”? Am rezolvat asta pe C3-ul meu: acum merg autentificarea și redarea cu abonament, fără VPN.

Am pus aici un asistent care te conduce prin pași. Descarci proiectul, pornești asistentul și alegi **Repară Apple TV**. El face backup, verifică fișierele și aplică schimbarea. [Tutorialul este aici](TUTORIAL.md).

Ai nevoie de un Mac sau Linux în aceeași rețea cu TV-ul, Node.js 20+, Python 3.9+ și aplicația LG Developer Mode. Nu trebuie să descarci separat aplicația Apple TV.

## Merge și pe alte LG-uri?

Asistentul are două profiluri exacte:

| Model | Firmware | SDK | Apple TV | Validare live |
| --- | --- | --- | --- | --- |
| C3 OLED77C31LA | 43.21.71 | 11.2.0 | 16.2.5 | Procedura inițială: autentificare și redare confirmate de proprietar. |
| C2 OLED77C21LA | 33.31.68 | 10.3.1 | 16.2.4 | Export și aplicare JS confirmate prin raport; redare și restaurare live încă neverificate. |

Fluxul unificat al asistentului este verificat offline pentru ambele profiluri. Alte modele sau versiuni sunt refuzate. [Detalii și raportare](COMPATIBILITY.md).

## De ce nu un IPK?

Am încercat o copie instalată separat: apăreau meniurile, dar autentificarea nu mergea. De aceea reparăm aplicația originală din TV.

Procedura folosește **root temporar** — acces de administrator cât se face reparația. Corecția rămâne, dar nu se instalează root la pornire. Din același asistent poți reveni la original, folosind backupul tău.

Înainte de export, deschide Apple TV din Home și las-o pornită, chiar dacă afișează eroarea regională. Corecția dezactivează actualizările JavaScript interne ale aplicației; acestea pot fi reactivate prin restaurarea originalelor.

Păstrează folderul `backup` pe calculator; nu îl publica. Pentru comenzile manuale există și [ghidul avansat](ADVANCED.md).
