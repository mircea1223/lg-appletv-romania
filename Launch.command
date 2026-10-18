#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# macOS: open this file to start the local guided installer in Terminal.
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Lipsește Python 3. Instalează-l de la https://www.python.org/downloads/"
  echo "Apoi deschide din nou acest fișier."
  read -r -p "Apasă Enter pentru închidere. "
  exit 1
fi
python3 install.py
installer_status=$?
echo
read -r -p "Apasă Enter pentru închidere. "
exit "$installer_status"
