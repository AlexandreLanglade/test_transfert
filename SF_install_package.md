C'est une étape très logique. Pour que l'installation ne s'exécute **qu'une seule fois** (après avoir traité toute la liste d'IP/VIP) et bénéficie du `commit` global, nous allons placer cette tâche dans le fichier principal `tasks/main.yml`, juste après la boucle et le commit, mais toujours à l'intérieur du bloc sécurisé par le `lock`.

Pour ce faire, on va introduire une nouvelle variable d'entrée : `suppression_flux_package_to_install`.

Voici les fichiers de ton rôle mis à jour :

---

## 📂 Mise à jour du Rôle `suppression_flux`

### 1. `defaults/main.yml`

On ajoute la nouvelle variable par défaut pour définir le nom du package à installer.

```yaml
---
suppression_flux_adom_targeted: ""
suppression_flux_package_to_install: "" # Nom du package à pousser (ex: "default")
suppression_flux_ip_to_delete_list: []

```

### 2. `tasks/main.yml`

C'est ici que l'étape **6) INSTALL** est ajoutée. Elle s'exécute après la fin de la boucle (`loop`) et après le `commit`.

```yaml
---
# ==========================================
# 0) LOCK DE L'ADOM TARGETÉ
# ==========================================
- name: "[{{ suppression_flux_adom_targeted }}] Verrouiller l'ADOM"
  fortinet.fortimanager.fmgr_dvmdb_adom_workspace_lock:
    adom: "{{ suppression_flux_adom_targeted }}"

- name: Bloc de traitement des suppressions et installation
  block:

    # 1) à 4) S'exécutent en boucle pour chaque IP/VIP
    - name: "Traiter chaque élément de la liste"
      include_tasks: delete_item.yml
      loop: "{{ suppression_flux_ip_to_delete_list }}"
      loop_control:
        loop_var: current_item

    # ==========================================
    # 5) ON COMMIT (Une fois que TOUT est nettoyé)
    # ==========================================
    - name: "[{{ suppression_flux_adom_targeted }}] Commit des modifications du Workspace"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_commit:
        adom: "{{ suppression_flux_adom_targeted }}"

    # ==========================================
    # 6) ON INSTALL LE POLICY PACKAGE
    # ==========================================
    # Cette tâche lance l'installation vers les FortiGates rattachés au package
    - name: "[{{ suppression_flux_adom_targeted }}] Installer le Policy Package '{{ suppression_flux_package_to_install }}'"
      fortinet.fortimanager.fmgr_securityconsole_install_package:
        securityconsole_install_package:
          adom: "{{ suppression_flux_adom_targeted }}"
          pkg: "{{ suppression_flux_package_to_install }}"
      # Sécurité : on n'exécute l'installation que si un nom de package a été fourni
      when: suppression_flux_package_to_install | length > 0

  always:
    # ==========================================
    # 7) ON UNLOCK L'ADOM (S'exécute quoi qu'il arrive, même si l'install échoue)
    # ==========================================
    - name: "[{{ suppression_flux_adom_targeted }}] Déverrouiller l'ADOM"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_unlock:
        adom: "{{ suppression_flux_adom_targeted }}"

```

*(Note : Le fichier `tasks/delete_item.yml` créé à l'étape précédente reste inchangé, il continue de s'occuper uniquement des suppressions unitaires et du nettoyage des règles via `none`).*

---

## 📋 Exemple d'appel dans ton Playbook principal

Dans ton playbook, il te suffit maintenant de rajouter la variable `suppression_flux_package_to_install` en lui donnant le nom du Policy Package correspondant à ton ADOM (par exemple celui vu dans tes calls bruno : `"SQFB2W01-SQFA2W01_SQF92W01"`).

```yaml
---
- name: Exécution du nettoyage des flux et installation via Rôle
  hosts: fortimanager
  connection: local
  gather_facts: false

  tasks:
    - name: "Appel du rôle de suppression et installation"
      include_role:
        name: suppression_flux
      vars:
        suppression_flux_adom_targeted: "STCv2_BRS_HP"
        # On définit le package à installer après le nettoyage
        suppression_flux_package_to_install: "SQFB2W01-SQFA2W01_SQF92W01"
        
        suppression_flux_ip_to_delete_list:
          - ip: "1.1.1.1"
            mask: "255.255.255.255"
            name: "addr.BRS_HP_TEST_BMO"
            type: "address"
          - ip: "2.2.2.2"
            mask: "255.255.255.255"
            name: "vip.BRS_HP_PROXY_WEB"
            type: "vip"

```

### 🎯 Pourquoi cette structure est optimale ?

1. **Performance :** FortiManager ne compile et ne pousse la configuration vers les pare-feux qu'**une seule fois** à la toute fin, plutôt que de le faire pour chaque IP de la liste.
2. **Idempotence et Sécurité :** Si le playbook plante au milieu des suppressions d'IP, l'étape de `commit` et d'`install` n'est pas atteinte, évitant ainsi de pousser une configuration partiellement nettoyée. L'ADOM sera quant à lui correctement déverrouillé grâce au bloc `always`.
