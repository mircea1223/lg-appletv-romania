# Tutorial: Apple TV România pe LG

**Pentru cine este:** configurația verificată este LG OLED77C31LA (C3), firmware 43.21.71, SDK webOS 11.2.0 și Apple TV 16.2.5 cu fișierele originale cunoscute. Pentru alte configurații, vezi [compatibilitatea](COMPATIBILITY.md) înainte de a continua. Acesta este un kit experimental: reparația inițială a funcționat pe C3, dar instrumentele portabile au fost testate numai offline.

Procedura păstrează aplicația originală și cere acces root doar pe durata operațiilor. Modificarea aplicației rămâne după încheierea accesului root. Pentru vizionare ai în continuare nevoie de propriul cont și dreptul de acces la conținut.

## Pregătire, o singură dată

Comenzile sunt pentru Terminal pe macOS sau Linux. Descarcă proiectul și intră în directorul lui:

```sh
git clone https://github.com/mircea1223/lg-appletv-romania.git
cd lg-appletv-romania
```

Rulează comenzile următoare din acest director. Ai nevoie de **Node.js 20+, npm, Python 3 și Git**. Calculatorul și TV-ul trebuie să se poată conecta între ele în aceeași rețea.

1. Pe TV, verifică modelul și firmware-ul din setări. Păstrează aplicația Apple TV originală instalată.
2. Instalează aplicația oficială **Developer Mode**, autentifică-te cu un cont LG Developer și activează **Dev Mode Status**. După repornire, deschide aplicația și activează **Key Server**. [Pașii oficiali LG](https://webostv.developer.lge.com/develop/getting-started/developer-mode-app).
3. Pe calculator, configurează conexiunea:

```sh
npm install -g @webos-tools/cli@3.2.6
ares-config --profile tv
ares-setup-device
```

În meniul de configurare adaugă dispozitivul **`tv`**, cu IP-ul televizorului, port **`9922`**, utilizator **`prisoner`**. Apoi:

```sh
ares-novacom --device tv --getkey
ares-device --system-info --device tv
ares-novacom --device tv --run 'id'
```

La `--getkey` introdu codul de șase caractere din Developer Mode. `id` trebuie să arate utilizatorul de dezvoltare, nu root. Compară modelul, firmware-ul și SDK-ul cu configurația de mai sus; dacă diferă, oprește procedura și raportează configurația pentru verificare.

Introdu IP-ul TV-ului tău când ți se cere. Variabila va fi folosită în toate comenzile următoare, în aceeași fereastră Terminal:

```sh
printf 'IP-ul televizorului: '
read -r TV_IP
```

Descarcă sursa loaderului fixat, **fără să rulezi varianta standard**:

```sh
git clone https://github.com/throwaway96/slopbro.git slopbro-source
git -C slopbro-source checkout 21023d56ca424607bb03d2939609cc658c655fc7
```

Kitul creează module proprii, fără `autoroot.sh`, Homebrew sau root persistent. Rulează numai `slopbro.py` din directoarele generate în pașii următori și păstrează `--asset-source dir`. Argumentul `11` este versiunea SDK testată; **nu îl înlocui cu numărul comercial webOS 26**. [Sursa loaderului](https://github.com/throwaway96/slopbro/tree/21023d56ca424607bb03d2939609cc658c655fc7).

## 1. Backup

Acest pas exportă fișierele statice ale aplicației, fără datele contului. Pregătește și pornește exportul:

```sh
python3 tools/prepare_bundle.py export \
  --upstream slopbro-source --output export-bundle

(cd export-bundle && python3 slopbro.py \
  --webos-version 11 --asset-source dir --debug "$TV_IP")
```

Acceptă asocierea afișată pe TV. Televizorul poate schimba temporar aplicația din prim-plan. După terminare, așteaptă câteva secunde, apoi descarcă rezultatul și backupul:

```sh
mkdir backup
export_result="$(python3 -c 'import json; print(json.load(open("export-bundle/bundle.json"))["receiptRemote"])')"
node tools/pull_file.cjs tv "$export_result" backup/export-result.json

archive_path="$(python3 -c 'import json; r=json.load(open("backup/export-result.json")); assert r["status"]=="success", r; print(r["archivePath"])')"
node tools/pull_file.cjs tv "$archive_path" backup/apple-tv-original.tar

python3 tools/verify_export.py \
  --archive backup/apple-tv-original.tar \
  --result backup/export-result.json --output original
```

**Continuă numai dacă toate comenzile reușesc.** Mesajul „all tracked files were requested” confirmă transferul loaderului, nu succesul operației. Confirmarea este rezultatul verificat și backupul extras.

După extragere, verifică amprentele fără să contactezi TV-ul:

```sh
python3 check_compatibility.py \
  --source original/media/cryptofs/apps/usr/palm/applications/com.apple.appletv \
  --image original/media/cryptofs/apps/usr/palm/data/images/com.apple.appletv/data.img
```

Un raport pozitiv confirmă numai fișierele cunoscute. Alte modele și firmware-uri rămân neverificate; vezi [COMPATIBILITY.md](COMPATIBILITY.md).

## 2. Corecție

Generează corecția din propria aplicație și verifică sintaxa. Nicio scriere pe TV în acest bloc:

```sh
python3 tools/build_patch.py \
  --source original/media/cryptofs/apps/usr/palm/applications/com.apple.appletv \
  --output patched

node --check patched/res/app.js
node --check patched/res/main.js

python3 tools/prepare_bundle.py apply \
  --upstream slopbro-source \
  --original original/media/cryptofs/apps/usr/palm/applications/com.apple.appletv \
  --cleanup-export export-bundle/bundle.json \
  --archive backup/apple-tv-original.tar --output apply-bundle
```

**Dacă apare `Unknown or modified` sau `Refused`, oprește-te.** Fișierele nu corespund versiunii analizate. Nu schimba amprentele și nu continua cu comenzile următoare.

Închide redarea pe TV, apoi aplică pachetul generat:

```sh
(cd apply-bundle && python3 slopbro.py \
  --webos-version 11 --asset-source dir --debug "$TV_IP")
```

Așteaptă câteva secunde și verifică rezultatul:

```sh
apply_result="$(python3 -c 'import json; print(json.load(open("apply-bundle/bundle.json"))["receiptRemote"])')"
node tools/pull_file.cjs tv "$apply_result" backup/apply-result.json
python3 -c 'import json; r=json.load(open("backup/apply-result.json")); print(json.dumps(r, indent=2)); assert r["status"]=="success"'
```

După succes, numai `res/app.js` și `res/main.js` sunt schimbate. Executabilul, bibliotecile, manifestul, imaginea instalată și datele contului sunt păstrate. Accesul root se încheie; fișierele temporare de lucru sunt curățate. Backupul de pe calculator rămâne.

## 3. Test

Din Home, deschide pictograma originală **Apple TV**:

1. Verifică meniurile și catalogul.
2. Alege **Sign In**, scanează codul QR și autentifică-te în fluxul oficial Apple.
3. Pornește **un episod complet cu abonament**. Testează câteva minute redarea, pauza și derularea.

Un trailer sau simpla apariție a meniurilor nu confirmă reușita. Nu instala o clonă ori un IPK cu ID-ul `com.apple.appletv` și nu dezinstala aplicația originală pentru această procedură.

Păstrează privat directorul `backup`, originalele extrase, pachetele generate și fișierele `.key`. Nu le încărca pe GitHub.

## Revenirea la original

Folosește propriul backup verificat. Restaurarea readuce numai cele două fișiere modificate; eroarea inițială de disponibilitate poate reapărea.

```sh
python3 tools/prepare_bundle.py restore \
  --upstream slopbro-source \
  --original original/media/cryptofs/apps/usr/palm/applications/com.apple.appletv \
  --output restore-bundle

(cd restore-bundle && python3 slopbro.py \
  --webos-version 11 --asset-source dir --debug "$TV_IP")
```

După câteva secunde:

```sh
restore_result="$(python3 -c 'import json; print(json.load(open("restore-bundle/bundle.json"))["receiptRemote"])')"
node tools/pull_file.cjs tv "$restore_result" backup/restore-result.json
python3 -c 'import json; r=json.load(open("backup/restore-result.json")); print(json.dumps(r, indent=2)); assert r["status"]=="success"'
```

Deschide din nou Apple TV. Nu dezarhiva întregul backup peste aplicație și nu șterge datele contului.

## Dacă ceva se oprește

| Mesaj sau problemă | Pasul următor |
| --- | --- |
| Conexiune refuzată sau eroare SSH | Verifică IP-ul, Developer Mode și Key Server; reia `--getkey` dacă este necesar. |
| TV-ul nu descarcă fișierele | Permite conexiunile din rețeaua locală către calculator; loaderul acceptă și `--local-ip` pentru adresa calculatorului. |
| `Unknown or modified`, `Refused`, alt SDK sau alt firmware | Oprește aplicarea și raportează configurația. |
| Nu găsești rezultatul | Așteaptă finalizarea. Nu confunda descărcarea pachetului cu execuția lui. |
| Eroare cu `committed: true` | Corecția a fost deja scrisă, dar curățarea a eșuat. Păstrează rezultatul și cere verificare; nu relua instalarea orbește. |
| Eroare de autentificare sau redare după aplicare | Notează etapa exactă și mesajul, fără parole sau coduri de autentificare. |

Directoarele de ieșire și fișierele descărcate trebuie să fie noi. Dacă ai mai rulat un pas, păstrează rezultatele pentru diagnostic; nu șterge backupul ca să faci loc unei noi încercări.
