C'est une excellente idée de transitionner vers un **rôle Ansible**. C'est beaucoup plus propre pour la réutilisabilité, et le fait de passer directement le `name` et le `type` en input est un énorme avantage : **on économise l'étape de recherche initiale**, ce qui rend le rôle plus rapide et plus fiable.

Voici l'architecture et le code de ton nouveau rôle `suppression_flux`.

---

## 📂 Structure du Rôle

Dans ton arborescence Ansible, crée la structure suivante :

```text
roles/
└── suppression_flux/
    ├── defaults/
    │   └── main.yml
    └── tasks/
        ├── main.yml
        └── delete_item.yml

```

---

## 🛠️ Code du Rôle

### 1. `defaults/main.yml`

On y définit les variables par défaut (vides ou exemples) pour documenter le rôle.

```yaml
---
suppression_flux_adom_targeted: ""
suppression_flux_ip_to_delete_list: []

```

### 2. `tasks/main.yml`

C'est le point d'entrée du rôle. Il s'occupe de gérer le cycle de vie de l'ADOM (Lock / Commit / Unlock) et appelle les tâches de suppression en boucle.

```yaml
---
# ==========================================
# 0) LOCK DE L'ADOM TARGETÉ
# ==========================================
- name: "[{{ suppression_flux_adom_targeted }}] Verrouiller l'ADOM"
  fortinet.fortimanager.fmgr_dvmdb_adom_workspace_lock:
    adom: "{{ suppression_flux_adom_targeted }}"

- name: Bloc de traitement des suppressions (Logique 'none')
  block:

    # On boucle sur la liste d'inputs fournie
    - name: "Traiter chaque élément de la liste"
      include_tasks: delete_item.yml
      loop: "{{ suppression_flux_ip_to_delete_list }}"
      loop_control:
        loop_var: current_item

    # ==========================================
    # 5) ON COMMIT (Une fois que tout est nettoyé)
    # ==========================================
    - name: "[{{ suppression_flux_adom_targeted }}] Commit des modifications du Workspace"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_commit:
        adom: "{{ suppression_flux_adom_targeted }}"

  always:
    # ==========================================
    # 7) ON UNLOCK L'ADOM (S'exécute quoi qu'il arrive)
    # ==========================================
    - name: "[{{ suppression_flux_adom_targeted }}] Déverrouiller l'ADOM"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_unlock:
        adom: "{{ suppression_flux_adom_targeted }}"

```

### 3. `tasks/delete_item.yml`

Ce fichier est exécuté pour chaque ligne de ta liste. Il utilise dynamiquement le `type` ("address" ou "vip") et le `name` fournis.

```yaml
---
# Ici, 'current_item' contient : ip, mask, name, type

# ==========================================
# 2) SUPPRESSION DE L'OBJET (Force -> Remplacement par 'none')
# ==========================================
- name: "[{{ suppression_flux_adom_targeted }}] Supprimer l'objet {{ current_item.name }} (Type: {{ current_item.type | upper }})"
  fortinet.fortimanager.fmgr_generic:
    method: "delete"
    params:
      - url: "pm/config/adom/{{ suppression_flux_adom_targeted }}/obj/firewall/{{ current_item.type }}"
        option: "force"
        filter: ["name", "==", "{{ current_item.name }}"]
  register: delete_status
  # Optionnel : Évite de planter si l'objet avait déjà été supprimé à la main
  failed_when: 
    - delete_status.meta.response_code is defined 
    - delete_status.meta.response_code < 0 
    - delete_status.meta.response_code != -3 # Code standard FortiManager pour "Object not found"

# ==========================================
# 3) RÉCUPÉRATION DES "none" POUR CET OBJET
# ==========================================
- name: "[{{ suppression_flux_adom_targeted }}] Lancer 'Where used' sur 'none' pour le type {{ current_item.type }}"
  fortinet.fortimanager.fmgr_generic:
    method: "exec"
    params:
      - url: "/cache/search/where/used/start"
        data:
          flags: ["direct used"]
          mkey: "none"
          obj: "adom/{{ suppression_flux_adom_targeted }}/obj/firewall/{{ current_item.type }}"
  register: where_used_start

- name: "[{{ suppression_flux_adom_targeted }}] Récupérer les détails du 'Where used'"
  fortinet.fortimanager.fmgr_generic:
    method: "exec"
    params:
      - url: "/cache/search/where/used/get/detail"
        token: "{{ where_used_start.meta.response_data[0].data.token }}"
  register: where_used_details

# ==========================================
# 4) LOOP - SUPPRESSION DES POLITIQUES AFECTÉES
# ==========================================
- name: "[{{ suppression_flux_adom_targeted }}] Supprimer les politiques contenant 'none' suite à la suppression de {{ current_item.name }}"
  fortinet.fortimanager.fmgr_generic:
    method: "delete"
    params:
      - url: "pm/config/adom/{{ suppression_flux_adom_targeted }}/pkg/{{ item.pkg }}/firewall/policy"
        filter: ["policyid", "==", "{{ item.policyid }}"]
  loop: "{{ where_used_details.meta.response_data[0].data.list | default([]) }}"
  when: item.type == 'policy'
  ignore_errors: true

```

---

## 📋 Exemple de Playbook pour appeler ton rôle

Voici comment tu vas pouvoir appeler ton rôle depuis un playbook principal (par exemple `playbook_nettoyage.yml`), en lui passant exactement ton format de variables :

```yaml
---
- name: Exécution du nettoyage des flux via Rôle
  hosts: fortimanager
  connection: local
  gather_facts: false

  tasks:
    - name: "Appel du rôle de suppression pour l'ADOM spécifié"
      include_role:
        name: suppression_flux
      vars:
        suppression_flux_adom_targeted: "STCv2_BRS_HP"
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

### 💡 Ce qui rend cette version très robuste :

* **Génération dynamique des URLs :** Grâce à `{{ current_item.type }}`, l'URL de l'API bascule automatiquement entre `.../obj/firewall/address` et `.../obj/firewall/vip`.
* **Le traitement séquentiel propre :** Si l'objet 1 génère des `none`, ils sont nettoyés. Puis l'objet 2 passe, génère ses `none`, et ils sont nettoyés à leur tour, le tout au sein du même Lock de session.

Tu valides cette structure sous forme de rôle ?
