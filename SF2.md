Pour traiter à la fois le cas d'une **IP classique** (objet Address) et d'une **VIP** (Virtual IP), nous devons adapter l'algorithme.

Le comportement de FortiManager avec les VIP est légèrement différent : une VIP mappe une adresse externe (IP publique/frontale) vers une adresse interne. Ton troisième appel Bruno (`2 Get VIP object with IP.bru`) montre d'ailleurs que tu cherches si ton IP d'entrée correspond soit à `extip` soit à `mappedip`.

Voici la logique mise à jour pour gérer dynamiquement les deux cas :

1. **Recherche de l'IP en tant qu'objet classique.**
2. **Recherche de l'IP en tant que VIP** (si l'objet classique n'est pas trouvé).
3. **Application de la suppression** (avec l'option `force`) sur le bon type d'objet trouvé.
4. **Recherche du `Where used` sur `none**` et nettoyage des politiques (la logique reste identique, car le fait de forcer la suppression d'une VIP va aussi générer des `none` dans les politiques qui l'utilisaient).

Voici les fichiers mis à jour pour ton playbook :

---

## 🛠️ Le fichier de tâches principal (`adom_cleanup.yml`)

Ce fichier va maintenant chercher le type d'objet (IP ou VIP) et aiguiller la suppression.

```yaml
---
# ==========================================
# 0) LOCK DE L'ADOM
# ==========================================
- name: "[{{ current_adom }}] Verrouiller l'ADOM"
  fortinet.fortimanager.fmgr_dvmdb_adom_workspace_lock:
    adom: "{{ current_adom }}"

- name: Execution du bloc de nettoyage (Gestion IP et VIP)
  block:

    # ==========================================
    # 1) RECHERCHE : CAS 1 - IP CLASSIQUE
    # ==========================================
    - name: "[{{ current_adom }}] Tester si l'IP est un objet Address"
      fortinet.fortimanager.fmgr_generic:
        method: "get"
        params:
          - url: "pm/config/adom/{{ current_adom }}/obj/firewall/address"
            fields: ["name", "type", "subnet"]
            filter:
              - ["subnet", "==", ["{{ ip_to_delete }}", "255.255.255.255"]]
      register: address_lookup

    # ==========================================
    # 1) RECHERCHE : CAS 2 - VIP (Si pas trouvé en IP classique)
    # ==========================================
    # Calqué sur ton call Bruno : filter extip == IP ou mappedip == IP
    - name: "[{{ current_adom }}] Tester si l'IP est une VIP"
      fortinet.fortimanager.fmgr_generic:
        method: "get"
        params:
          - url: "pm/config/adom/{{ current_adom }}/obj/firewall/vip"
            fields: ["name", "extip", "mappedip"]
            filter:
              - ["extip", "==", "{{ ip_to_delete }}"]
              - "||"
              - ["mappedip", "==", "{{ ip_to_delete }}"]
      register: vip_lookup
      when: address_lookup.meta.response_data[0] is not defined

    # ==========================================
    # DÉTERMINATION DU TYPE ET DU NOM D'OBJET
    # ==========================================
    - name: "[{{ current_adom }}] Identifier l'objet trouvé"
      set_fact:
        object_type: "{{ 'address' if address_lookup.meta.response_data[0] is defined else ('vip' if (vip_lookup.meta.response_data is defined and vip_lookup.meta.response_data[0] is defined) else 'unknown') }}"
        detected_name: "{{ address_lookup.meta.response_data[0].name if address_lookup.meta.response_data[0] is defined else (vip_lookup.meta.response_data[0].name if (vip_lookup.meta.response_data is defined and vip_lookup.meta.response_data[0] is defined) else '') }}"

    # Si l'IP n'est ni une adresse ni une VIP dans cet ADOM, on passe à l'ADOM suivant
    - name: "[{{ current_adom }}] Stop si l'IP/VIP n'existe pas"
      meta: end_host
      when: object_type == 'unknown'

    # ==========================================
    # 2) SUPPRESSION DE L'OBJET (IP ou VIP)
    # ==========================================
    - name: "[{{ current_adom }}] Supprimer l'objet (Type: {{ object_type | upper }}) via Force"
      fortinet.fortimanager.fmgr_generic:
        method: "delete"
        params:
          - url: "pm/config/adom/{{ current_adom }}/obj/firewall/{{ object_type }}"
            option: "force"
            filter: ["name", "==", "{{ detected_name }}"]

    # ==========================================
    # 3) RECHERCHE DES "none" GENERES
    # ==========================================
    - name: "[{{ current_adom }}] Lancer la recherche 'Where used' sur l'objet 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "exec"
        params:
          - url: "/cache/search/where/used/start"
            data:
              flags: ["direct used"]
              mkey: "none"
              # On cherche dans le bon répertoire selon ce qu'on a supprimé
              obj: "adom/{{ current_adom }}/obj/firewall/{{ object_type }}"
      register: where_used_start

    - name: "[{{ current_adom }}] Récupérer les détails du 'Where used' pour 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "exec"
        params:
          - url: "/cache/search/where/used/get/detail"
            token: "{{ where_used_start.meta.response_data[0].data.token }}"
      register: where_used_details

    # ==========================================
    # 4) LOOP - SUPPRESSION DES POLITIQUES
    # ==========================================
    - name: "[{{ current_adom }}] Supprimer les politiques contenant 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "delete"
        params:
          - url: "pm/config/adom/{{ current_adom }}/pkg/{{ item.pkg }}/firewall/policy"
            filter: ["policyid", "==", "{{ item.policyid }}"]
      loop: "{{ where_used_details.meta.response_data[0].data.list | default([]) }}"
      when: item.type == 'policy'
      ignore_errors: true

    # ==========================================
    # 5) COMMIT
    # ==========================================
    - name: "[{{ current_adom }}] Commit des modifications du Workspace"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_commit:
        adom: "{{ current_adom }}"

  always:
    # ==========================================
    # 7) UNLOCK
    # ==========================================
    - name: "[{{ current_adom }}] Déverrouiller l'ADOM"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_unlock:
        adom: "{{ current_adom }}"

```

---

## 💡 Ce qui change dans cette version :

1. **Variables dynamiques (`object_type`)** : Le script utilise une condition Jinja (`set_fact`) pour déterminer si l'URL de l'API cible finale doit se terminer par `obj/firewall/address` ou `obj/firewall/vip`.
2. **Filtre de suppression par Nom** : À l'étape 2, pour éviter de réécrire des filtres de sous-réseaux complexes pour la VIP, on utilise directement le paramètre `filter: ["name", "==", "{{ detected_name }}"]`. C'est plus simple et plus sûr car on a validé son existence juste avant.
3. **Adaptation du chemin de recherche `Where used**` : L'argument `obj` passé à la recherche `none` s'adapte lui aussi automatiquement (`obj/firewall/address` ou `obj/firewall/vip`) pour cibler exactement d'où provient le `none`.

Tu peux utiliser ce playbook de manière transparente, que ta variable `ip_to_delete` contienne une IP d'hôte classique ou une IP associée à une VIP !
