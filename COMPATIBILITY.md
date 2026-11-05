# Compatibilitatea cu alte televizoare LG

**Autentificarea și redarea conținutului cu abonament au fost confirmate pe un singur televizor:** LG C3 **OLED77C31LA**, firmware **43.21.71**, SDK webOS **11.2.0**, aplicație Apple TV originală **16.2.5**. Există și un profil experimental C2 **OLED77C21LA / 33.31.68 / SDK 10.3.1 / Apple TV 16.2.4**, cu export și aplicare confirmate prin rapoarte live. Redarea, persistența după restart și restaurarea C2 nu sunt încă confirmate. Instrumentele offline nu testează redarea.

| Configurație | Ce știm |
| --- | --- |
| OLED77C31LA, firmware 43.21.71, SDK 11.2.0, pachetul original verificat | Procedura inițială a funcționat; autentificare și redare confirmate de proprietar. |
| Alt exemplar, diagonală sau variantă regională C3 | Compatibilitate neverificată; numele C3 nu este suficient. |
| OLED77C21LA, firmware 33.31.68, SDK 10.3.1, Apple TV 16.2.4 | Export și aplicare confirmate prin rapoarte; redarea și restaurarea live neverificate. |
| C1, alte C2, C4, C5, alte OLED, QNED sau LCD LG | Compatibilitate neverificată. |
| Același model după actualizarea firmware-ului sau a aplicației | Este necesară o nouă verificare. |
| Aplicația Apple TV originală lipsește | Acest kit nu o instalează și nu furnizează un IPK Apple. |

Asistentul unificat este testat offline pentru ambele profiluri, inclusiv aplicare/restaurare simulate și refuzul backupurilor din alt profil. Operațiile C2 live au fost executate prin pachetele avansate generate local. Nu trata existența kitului ca pe o certificare pentru alte modele.

## UID-ul Developer Mode

`developer_mode_profiles.json` leagă UID-urile acceptate de combinația exactă model / firmware / SDK. Asistentul citește UID-ul real al utilizatorului `prisoner` înainte de orice operație root, îl acceptă numai dacă apare în profilul unic corespunzător și îl include în pachetele temporare. Nu edita un profil pentru un model sau firmware neconfirmat: UID-ul este folosit pentru drepturile asupra backupului și rapoartelor preluate de pe TV.

Profilurile incluse permit UID 6303 sau 6322 pentru C3 și UID 6322 pentru C2. Modelul real selectează profilul înainte de validarea UID-ului. Adăugarea unui model în JSON nu adaugă suport de patch: metadatele, hash-urile și layoutul sunt validate separat. UID-ul este recitit înainte de fiecare operație root.

## Verificarea simplă a fișierelor

Asistentul `install.py` face verificarea automat și salvează raportul `compatibility.json` în directorul privat `backup/session-...`. Verifică modelul, firmware-ul și SDK-ul prin conexiunea LG înainte de orice operație root. Dacă nu corespund unuia dintre cele două profiluri exacte, nu încearcă aplicarea.

Comanda de mai jos este pentru exportul manual din [ghidul avansat](ADVANCED.md), rulat din rădăcina kitului:

```sh
python3 check_compatibility.py \
  --source original/media/cryptofs/apps/usr/palm/applications/com.apple.appletv \
  --image original/media/cryptofs/apps/usr/palm/data/images/com.apple.appletv/data.img \
  --model OLED77C31LA --firmware 43.21.71 --sdk 11.2.0 \
  > compatibility.json
```

Înlocuiește modelul și versiunile cu valorile televizorului tău. `--image` este opțional pentru această comparație offline; tranzacția pe TV verifică obligatoriu imaginea originală. Comanda citește numai cele cinci fișiere statice analizate și, dacă este indicată, imaginea `data.img`. Nu se conectează la televizor și nu schimbă fișiere.

- `known-input-fingerprints-match` și codul de ieșire `0`: cele trei resurse JavaScript, executabilul și manifestul au amprentele originale cunoscute; imaginea corespunde și ea dacă ai furnizat-o. Acesta este un rezultat despre fișierele exportate, nu o aprobare de instalare.
- `unknown-or-modified-inputs` și codul `1`: cel puțin un fișier lipsește, este diferit sau nu poate fi citit sigur. Oprește procedura. Sunt refuzate și fișierele deja corectate; această comandă cere originalul din backup.
- `invalid-source` și codul `2`: directorul sursă nu este valid. Corectează calea.

`suppliedMetadataMatchesReference` compară numai valorile introduse de tine. Chiar dacă este `true`, verificatorul păstrează `playbackConfirmed: false` pentru televizorul curent. Nu verifică singur firmware-ul, accesul root, montările sau funcționarea contului. Cele cinci amprente nu dovedesc egalitatea tuturor fișierelor aplicației; de aceea raportul nu pretinde că întregul pachet a fost verificat.

Pentru exportul C2 folosește și `--profile c2`. Cele trei resurse JS sunt identice cu referința C3, însă executabilul, manifestul și imaginea instalată au hash-uri C2 separate, fixate în `tools/c2_profile.py`.

## Condițiile suplimentare pentru alt LG

1. **Pachetul original și identitatea nativă.** Aplicația trebuie să existe sub ID-ul `com.apple.appletv`, cu executabilul `AppleTV`, tip `native`, `trustLevel: trusted` și `privilegedJail: true`. Un număr de versiune egal, fără amprente egale, nu este suficient. O clonă cu alt ID a încărcat meniurile, dar a eșuat la autentificare în cazul nostru. Păstrează executabilul, bibliotecile native, manifestul, imaginea instalată și datele contului.
2. **Mecanismul root pe firmware-ul exact.** Loaderul provine din commitul SlopBro fixat în tutorial. Compatibilitatea loaderului și compatibilitatea corecției Apple sunt două verificări separate. Proiectul original raportează utilizări pe mai multe versiuni webOS, dar acestea nu confirmă această procedură pe fiecare model. Varianta standard instalează persistență; kitul folosește module proprii, fără `autoroot.sh`. [Sursa SlopBro fixată](https://github.com/throwaway96/slopbro/blob/21023d56ca424607bb03d2939609cc658c655fc7/README.md).
3. **Structura de fișiere și permisiunile.** Ambele profiluri cer deja un overlay inscriptibil la `/media/cryptofs/apps/usr/palm/applications/com.apple.appletv`. C3 cere `upperdir=/media/data/data/com.apple.appletv`. C2 cere exact lowerdir `/media/squashfs/apps/com.apple.appletv/usr/palm/applications/com.apple.appletv`, upperdir egal cu calea de instalare și workdir `/media/squashfs/work/com.apple.appletv`. Ambele cer `res` cu UID 0, GID 5000, mod `0775`, iar resursele cu UID 0, GID 5000, mod `0644`. Nu creează un overlay nou și nu remontează firmware-ul.
4. **Mediul modulului temporar.** Sunt verificate directoarele de lucru, identitatea procesului original prin `/proc`, API-urile Node de fișiere sigure, `O_NOFOLLOW` și `O_DIRECTORY`, precum și locația rezultatului în `/media/developer/temp`. Exportul mai cere `/bin/tar`, `/bin/df`, cel puțin 256 MiB liberi și spațiu suplimentar pentru copie. Layoutul, UID-urile sau API-urile diferite necesită o analiză separată, nu relaxarea verificărilor.
5. **Conexiunea și testul real.** Developer Mode asigură transferul SSH; nu oferă singur privilegiile aplicației originale. Verifică SDK-ul și firmware-ul cu `ares-device --system-info --device tv`. Nu folosi denumirea comercială `26` ca înlocuitor automat pentru argumentul testat `--webos-version 11`. După aplicare trebuie verificate codul QR, autentificarea, un episod complet cu abonament, pauza, reluarea și derularea. [Instrucțiunile LG pentru Developer Mode și informațiile dispozitivului](https://webostv.developer.lge.com/develop/getting-started/developer-mode-app).

Nu elimina verificările SHA256, de identitate, montare sau permisiuni pentru a forța un alt model. O diferență trebuie înțeleasă și o variantă nouă trebuie testată separat. Un update Apple poate înlocui corecția sau poate face corecția inutilă; fișierele noi necesită analiză înainte de reutilizarea kitului.

## Testele asistentului

Testele folosesc comenzi simulate și fișiere sintetice. Nu se conectează la TV și nu execută loaderul:

```sh
python3 -m unittest discover -s tests
```

Aceste teste verifică ordinea pașilor și oprirea la erori. Nu confirmă autentificarea sau redarea pe un televizor nou.

## Cum se raportează un alt model

Poți publica modelul exact, firmware-ul, SDK-ul, versiunea Apple TV, raportul JSON de mai sus și rezultatul testului de autentificare/redare. Raportul nu include chei sau date de cont. Nu publica backupul Apple, pachetele generate local, fișiere `.key`, coduri QR, passphrase-uri sau datele contului. O nouă intrare de compatibilitate se adaugă numai după un test real; meniurile sau un trailer singur nu confirmă redarea protejată.
