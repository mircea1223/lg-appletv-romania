# Apple TV România pe LG webOS

Corecție neoficială pentru aplicația **Apple TV originală**, atunci când afișează „Apple TV is not available” în România. Păstrează interfața, autentificarea și redarea native.

**Rezultat confirmat pe un singur televizor:** LG C3 OLED77C31LA, firmware 43.21.71, SDK webOS 11.2.0, Apple TV 16.2.5. Proprietarul a confirmat autentificarea și redarea conținutului cu abonament. Kitul portabil din acest repository a fost verificat **numai offline**; exportul, aplicarea și restaurarea din kit nu au fost încă repetate pe un TV.

## Cum se folosește

Urmează [tutorialul în trei etape](TUTORIAL.md): **backup → corecție → test**. Ai nevoie de aplicația Apple TV deja instalată, un calculator în aceeași rețea, Developer Mode, Node.js 20+, Python 3 și Git.

Nu există un IPK universal pe care îl instalezi și gata. O clonă cu alt ID a încărcat meniurile, dar a eșuat la autentificare. Procedura repară local `com.apple.appletv`, cu identitatea și privilegiile originale.

Repository-ul conține instrumentele și instrucțiunile. Aplicația Apple nu este distribuită: îți extragi copia instalată și păstrezi backupul privat.

## Compatibilitate

| Configurație | Stadiu |
| --- | --- |
| OLED77C31LA / 43.21.71 / SDK 11.2.0 / Apple TV 16.2.5 cu amprentele cunoscute | Reparația inițială confirmată; kitul portabil verificat offline |
| Alte diagonale sau variante C3 | Neverificat |
| C1, C2, C4, C5, seriile B/G și alte LG | Neverificat |
| Alt firmware, altă versiune a aplicației sau amprente diferite | Necesită analiză separată |
| TV fără aplicația Apple TV originală instalată | Nu este acoperit de această metodă |

Același nume de model sau același număr al aplicației nu dovedește compatibilitatea. Instrumentele verifică fișierele și structura instalării; nu certifică toate modelele LG. Nu elimina verificările SHA256 pentru a forța aplicarea.

Raportul offline al fișierelor și condițiile pentru alte modele sunt în [COMPATIBILITY.md](COMPATIBILITY.md). După export poți rula `python3 check_compatibility.py --source CALE_CĂTRE_ORIGINAL`; un rezultat pozitiv nu confirmă redarea pe alt televizor.

## Ce schimbă

Sunt modificate numai `res/app.js` și `res/main.js`: se completează configurația lipsă pentru România și se adaptează cererea de configurare a catalogului RO. Playerul, autentificarea, DRM, executabilul, bibliotecile și manifestul aplicației rămân originale. Încărcarea automată a actualizării JavaScript este oprită pentru a păstra corecția; după un update al aplicației este necesară o nouă verificare.

Accesul **root este temporar** și se încheie după fiecare operație. **Corecția aplicației rămâne instalată.** Kitul nu instalează Homebrew sau root la pornire. [Restaurarea](TUTORIAL.md#revenirea-la-original) readuce cele două fișiere din propriul backup.

Metoda folosește un loader derivat din [SlopBro, commit fixat](https://github.com/throwaway96/slopbro/tree/21023d56ca424607bb03d2939609cc658c655fc7), cu modulul standard de instalare înlocuit. **Nu rula SlopBro standard sau `autoroot.sh`**: acestea nu sunt procedura documentată aici. Licența și proveniența sunt în [tools/COPYING](tools/COPYING) și [tools/PROVENANCE.json](tools/PROVENANCE.json).

## Rapoarte pentru alte LG

Pentru o verificare nouă, publică într-un issue doar modelul complet, firmware-ul, SDK-ul webOS, versiunea Apple TV și eroarea. Un rezultat „meniurile apar” nu confirmă autentificarea sau redarea protejată. Nu publica arhiva aplicației, pachetele generate, parole, coduri QR de autentificare, fișiere `.key` sau chei SSH.
