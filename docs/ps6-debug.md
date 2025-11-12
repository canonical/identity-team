# PS6 Debugging instructions

This document serves as a knowledge base for debugging and fixing common issues on our cd cluster in PS6.

## Cilium pod is failing to start because of timeout

### When this happens

SSH to any node in the cluster and check if cilium pods are all healthy:
```console
sudo k8s kubectl get pods -n kube-system -o wide
```

If any of them are not ready, you can try to:
- Describe the pods
- Hop into the container and check the cilium logs:
```console
sudo less /var/run/cilium/cilium-cni.log
```

If you see any timeout issues when the pod is starting, then it is most likely this problem.

### How to fix it

- Delete the webhook:
```console
sudo k8s kubectl delete --all mutatingwebhookconfiguration
```

- Find broken node with:
```console
sudo k8s get pods -n kube-system -o wide
```

- On each broken node:

  * Stop k8s and kubeproxy (this is necesary because it would try to recreate the cilium resources):
  ```console
  sudo systemctl stop snap.k8s.kubelet snap.k8s.kube-proxy
  ```

  * Clean up cilium:
  ```console
  sudo rm -rf /var/run/cilium/cilium.pid && sudo /opt/cni/bin/cilium-dbg post-uninstall-cleanup --all-state --force
  ```

  * Reboot the node:
  ```console
  reboot
  ```

## Unseal vault

### When this happens

Vault periodically seals itself. Usually the first symptom of vault being sealed is that jimm is failing (e.g. the jwks endpoint will stop working).

To see if vault is sealed:

- Hop on to the cd nodes:
```console
ssh cd-k8s-leader
```

- Initialize the necessary env vars and check the vault status:
```console
export VAULT_CAPATH=$(pwd)/vault.pem; echo "Setting VAULT_CAPATH from" "$VAULT_CAPATH"
export VAULT_ADDR=https://$(juju status vault/leader --format=yaml | yq '.applications.vault.address'):8200; echo "Vault address=" "$VAULT_ADDR"
```

### How to fix it

- SSH to leader:
```console
ssh cd-k8s-leader
```

- Unseal vault, the key should be on `~/vault_unseal_key.txt`:
```console
export VAULT_ADDR=https://$(juju status vault/leader --format=yaml | yq '.applications.vault.address'):8200; echo "Vault address =" "$VAULT_ADDR"
export VAULT_CAPATH=$(pwd)/vault.pem; echo "Setting VAULT_CAPATH from" "$VAULT_CAPATH"
key_init=$(vault operator init -key-shares=1 -key-threshold=1); echo "$key_init"
vault operator unseal $(cat vault_unseal_key.txt)
```
