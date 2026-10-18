# Cum repari Apple TV pe LG

Ghidul este pentru aplicația Apple TV **deja instalată**, care afișează „Apple TV is not available” în România. Ai în continuare nevoie de contul și abonamentul tău Apple.

Reparația inițială a mers pe **C3 OLED77C31LA / firmware 43.21.71 / SDK 11.2.0 / Apple TV 16.2.5**. Asistentul de mai jos este nou și a fost testat numai offline. Pe alte configurații se oprește înainte de root; [alte LG-uri încă nu sunt confirmate](COMPATIBILITY.md).

## 1. Pregătește calculatorul

Folosește un **Mac sau Linux**, conectat la aceeași rețea cu televizorul. Windows nu este acoperit de acest asistent.

1. Instalează [Node.js](https://nodejs.org/en/download), versiunea 20 sau mai nouă.
2. Instalează [Python 3](https://www.python.org/downloads/), versiunea 3.9 sau mai nouă.
3. Deschide [pagina proiectului](https://github.com/mircea1223/lg-appletv-romania), apasă **Code → Download ZIP** și dezarhivează fișierul. Păstrează folderul undeva unde îl găsești ușor.

Nu ai nevoie de Git. Asistentul descarcă singur fișierele necesare și, dacă lipsește utilitarul oficial LG, îți propune instalarea lui.

## 2. Pregătește televizorul

1. Lasă aplicația **Apple TV originală** instalată.
2. Caută **Developer Mode** în magazinul LG și instaleaz-o.
3. Deschide Developer Mode și conectează-te cu un cont LG Developer. Dacă nu ai unul, [îl poți crea aici](https://webostv.developer.lge.com/).
4. Activează **Dev Mode Status**. Televizorul repornește.
5. Deschide din nou Developer Mode și activează **Key Server**.
6. Lasă pe ecran adresa **IP** și codul **Passphrase**. Asistentul le va cere pe calculator.

[Instrucțiunile LG, cu imagini](https://webostv.developer.lge.com/develop/getting-started/developer-mode-app).

## 3. Pornește asistentul

Pe Mac, deschide folderul dezarhivat și dă dublu clic pe **Launch.command**. Dacă nu se deschide, sau folosești Linux, deschide Terminal în acel folder și rulează:

```sh
python3 install.py
```

Introdu IP-ul televizorului când ți-l cere. La pasul de conectare, introdu codul **Passphrase** afișat în Developer Mode. Nu este parola contului Apple sau LG.

Meniul are trei opțiuni:

- **1. Verifică televizorul (fără root)** — îți arată dacă modelul și versiunile corespund.
- **2. Repară Apple TV (backup + root temporar)** — face backup, verifică aplicația și aplică reparația.
- **3. Restaurează din backup** — revine la fișierele originale.

Alege **2** pentru reparație; asistentul verifică singur televizorul înainte să continue. Opțiunea **1** este pentru verificare separată. Urmează mesajele din fereastră și acceptă asocierea pe TV dacă apare. Nu închide fereastra până când asistentul termină.

Backupul se păstrează în folderul **backup** al proiectului. Nu îl șterge și nu îl încărca pe GitHub.

## 4. Verifică dacă merge

Deschide pictograma obișnuită **Apple TV** din Home, autentifică-te și pornește un episod inclus în abonament. Lasă-l câteva minute, apoi încearcă pauza și derularea. Meniurile sau un trailer nu sunt suficiente pentru verificare.

Reparația rămâne instalată după terminare. Accesul root se încheie; nu se instalează root la pornirea televizorului.

## Dacă vrei să revii la original

Pornește același asistent, alege **3** și selectează backupul din lista afișată. După restaurare, eroarea inițială poate reveni.

Dacă asistentul se oprește, păstrează mesajul și [deschide un issue](https://github.com/mircea1223/lg-appletv-romania/issues/new/choose) cu modelul, firmware-ul și eroarea. Nu modifica verificările ca să forțezi instalarea și nu trimite parole, coduri de autentificare sau backupul. Pentru pașii manuali: [ghidul avansat](ADVANCED.md).
