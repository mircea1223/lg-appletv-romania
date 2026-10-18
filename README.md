# Apple TV pe LG, în România

Ai Apple TV instalat pe LG, dar apare „Apple TV is not available”? Am rezolvat asta pe C3-ul meu: acum merg autentificarea și redarea cu abonament, fără VPN.

Am pus aici un asistent care te conduce prin pași. Descarci proiectul, pornești asistentul și alegi **Repară Apple TV**. El face backup, verifică fișierele și aplică schimbarea. [Tutorialul este aici](TUTORIAL.md).

Ai nevoie de un Mac sau Linux în aceeași rețea cu TV-ul, Node.js 20+, Python 3.9+ și aplicația LG Developer Mode. Nu trebuie să descarci separat aplicația Apple TV.

## Merge și pe alte LG-uri?

Deocamdată, reparația a fost confirmată doar pe **LG C3 OLED77C31LA, firmware 43.21.71, SDK 11.2.0, Apple TV 16.2.5**. Noul asistent a fost verificat numai offline, nu rulat încă pe TV. El verifică modelul și versiunile înainte să aplice ceva și se oprește dacă diferă. [Detalii și raportare pentru alte modele](COMPATIBILITY.md).

## De ce nu un IPK?

Am încercat o copie instalată separat: apăreau meniurile, dar autentificarea nu mergea. De aceea reparăm aplicația originală din TV.

Procedura folosește **root temporar** — acces de administrator cât se face reparația. Corecția rămâne, dar nu se instalează root la pornire. Din același asistent poți reveni la original, folosind backupul tău.

Păstrează folderul `backup` pe calculator; nu îl publica. Pentru comenzile manuale există și [ghidul avansat](ADVANCED.md).
