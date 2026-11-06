#!/usr/bin/env bash
# One-time GitHub publish, so the Deploy buttons in README point at YOUR repo.
#
#   ./publish.sh your-github-username
#
# It rewrites the GITHUB_USER placeholder, makes a repo (via gh if installed,
# otherwise tells you the two commands to run), and pushes.
set -euo pipefail
cd "$(dirname "$0")"

USER_NAME="${1:-}"
if [ -z "$USER_NAME" ]; then
  echo "usage: ./publish.sh <github-username>"
  exit 1
fi

REPO="ssc-marks-bot"

echo "==> rewriting GITHUB_USER -> $USER_NAME"
for f in README.md app.json render.yaml; do
  [ -f "$f" ] && sed -i.bak "s/GITHUB_USER/$USER_NAME/g" "$f" && rm -f "$f.bak"
done

echo "==> git init"
git init -b main >/dev/null 2>&1 || true
git add -A
git commit -m "SSC marks analyser: link in, section-wise score out" >/dev/null || true

if command -v gh >/dev/null 2>&1; then
  echo "==> creating https://github.com/$USER_NAME/$REPO and pushing"
  gh repo create "$USER_NAME/$REPO" --public --source=. --push --description \
    "SSC response sheet -> section-wise marks" || {
      git remote remove origin 2>/dev/null || true
      git remote add origin "https://github.com/$USER_NAME/$REPO.git"
      git push -u origin main
    }
else
  echo
  echo "gh (GitHub CLI) nahi mila. Do commands chala do:"
  echo "  git remote add origin https://github.com/$USER_NAME/$REPO.git"
  echo "  git push -u origin main"
  echo
  echo "(repo pehle github.com/new se bana lena, naam: $REPO)"
fi

cat <<EOF

==> done. Buttons ab ye hain:

Render : https://render.com/deploy?repo=https://github.com/$USER_NAME/$REPO
Heroku : https://heroku.com/deploy?template=https://github.com/$USER_NAME/$REPO

README me badges already isi URL pe set ho gaye hain.
EOF
