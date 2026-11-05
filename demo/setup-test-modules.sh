#!/usr/bin/env bash
set -euo pipefail

O=floriandevries

run() {
  echo "+ $*"
  "$@"
}

run gh repo rename terraform-azurerm-fjdev-res-logic-app-standard -R "$O/terraform-azurerm-cgk-res-logic-app-standard" --yes
run gh repo rename terraform-azurerm-fjdev-res-mssql-managed-instance -R "$O/terraform-azurerm-cgk-res-mssql-managed-instance" --yes

run gh repo edit "$O/terraform-azurerm-fjdev-res-logic-app-standard" --remove-topic cgk
run gh repo edit "$O/terraform-azurerm-fjdev-res-mssql-managed-instance" --remove-topic cgk

run gh repo edit "$O/terraform-azurerm-fjdev-res-resource-group" --add-topic terraform --add-topic azurerm
run gh repo edit "$O/terraform-azurerm-cgk-res-resource-group" --remove-topic azurerm

for r in terraform-azurerm-subscription terraform-azurerm-vpn-server-configuration terraform-azurerm-point-to-site-vpn-gateway; do
  run gh repo edit "$O/$r" --remove-topic azurerm
done

for r in terraform-azurerm-fjdev-res-resource-group terraform-azurerm-fjdev-res-logic-app-standard terraform-azurerm-fjdev-res-mssql-managed-instance; do
  run gh repo edit "$O/$r" --visibility public --accept-visibility-change-consequences
done
