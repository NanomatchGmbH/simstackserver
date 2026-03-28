#!/bin/bash
# Dry-run stub for Deposit WaNo — creates placeholder output files without
# requiring a real Deposit installation.

echo "Deposit dry-run: creating placeholder output files"

echo "<molecule/>" > structure.cml
echo "<molecule/>" > structurePBC.cml
echo "# placeholder merged forcefield" > merged.spf
zip -q restartfile.zip structure.cml

echo "Deposit dry-run complete"
