VOIR LA CONNECTION DANS LE PB D'OUVERTURE

```yaml
---
- name: Algorithme de nettoyage d'IP sur FortiManager
  hosts: fortimanager
  connection: local
  gather_facts: false

  vars:
    ip_to_delete: "1.1.1.1"
    adom_list:
      - "NOM_ADOM"

  tasks:
    - name: "Boucle principale - Pour chaque ADOM"
      include_tasks: adom_cleanup.yml
      loop: "{{ adom_list }}"
      loop_control:
        loop_var: current_adom
```

C'est noté ! Si ton organisation a validé cette méthode et que tu acceptes le risque de balayer les `none` historiques, on va s'en tenir à ton algorithme initial. C'est l'avantage d'Ansible : on peut lui faire automatiser exactement la logique que tu as validée manuellement.

Dans ce cas, on repasse sur ton idée d'origine :

1. Suppression de l'objet IP avec l'option `force` (ce qui génère les `none` dans les règles).
2. Recherche `Where used` sur l'objet universel `none`.
3. Suppression des politiques associées.

Voici la mise à jour de ton fichier de tâches **`adom_cleanup.yml`** configuré selon tes exigences exactes :

```yaml
---
# ==========================================
# 0) LOCK DE L'ADOM
# ==========================================
- name: "[{{ current_adom }}] Verrouiller l'ADOM"
  fortinet.fortimanager.fmgr_dvmdb_adom_workspace_lock:
    adom: "{{ current_adom }}"

- name: Execution du bloc de nettoyage (Logique 'none')
  block:

    # ==========================================
    # 1) RÉCUPÉRATION DU HOSTNAME VIA L'IP
    # ==========================================
    - name: "[{{ current_adom }}] Récupérer le hostname de l'IP"
      fortinet.fortimanager.fmgr_generic:
        method: "get"
        params:
          - url: "pm/config/adom/{{ current_adom }}/obj/firewall/address"
            fields: ["name", "type", "subnet"]
            filter:
              - ["subnet", "==", ["{{ ip_to_delete }}", "255.255.255.255"]]
      register: address_lookup

    - name: "[{{ current_adom }}] Définir le hostname trouvé en variable"
      set_fact:
        detected_hostname: "{{ address_lookup.meta.response_data[0].name | default('') }}"

    # Si l'IP n'est pas trouvée, on arrête pour cet ADOM
    - name: "[{{ current_adom }}] Stop si l'IP n'existe pas"
      meta: end_host
      when: detected_hostname == ""

    # ==========================================
    # 2) SUPPRESSION DE L'OBJET ADDRESS (Option force)
    # ==========================================
    # Calqué sur ton call Bruno "Delete IP" avec l'option force
    - name: "[{{ current_adom }}] Supprimer l'objet Address (Force -> Remplacement par 'none')"
      fortinet.fortimanager.fmgr_generic:
        method: "delete"
        params:
          - url: "pm/config/adom/{{ current_adom }}/obj/firewall/address"
            option: "force"
            filter:
              - ["subnet", "==", ["{{ ip_to_delete }}", "255.255.255.255"]]

    # ==========================================
    # 3) RÉCUPÉRATION DES OBGETS OÙ "none" EST UTILISÉ
    # ==========================================
    - name: "[{{ current_adom }}] Lancer la recherche 'Where used' sur l'objet 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "exec"
        params:
          - url: "/cache/search/where/used/start"
            data:
              flags: ["direct used"]
              mkey: "none"
              obj: "adom/{{ current_adom }}/obj/firewall/address"
      register: where_used_start

    - name: "[{{ current_adom }}] Récupérer les détails du 'Where used' pour 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "exec"
        params:
          - url: "/cache/search/where/used/get/detail"
            token: "{{ where_used_start.meta.response_data[0].data.token }}"
      register: where_used_details

    # ==========================================
    # 4) LOOP - SUR LES OBGETS RÉCUPÉRÉS (SUPPRESSION DES POLITIQUES)
    # ==========================================
    # On boucle directement sur le résultat du "Where Used" de "none"
    - name: "[{{ current_adom }}] Supprimer les politiques contenant 'none'"
      fortinet.fortimanager.fmgr_generic:
        method: "delete"
        params:
          - url: "pm/config/adom/{{ current_adom }}/pkg/{{ item.pkg }}/firewall/policy"
            filter: ["policyid", "==", "{{ item.policyid }}"]
      # On cible l'arborescence du JSON retourné par FortiManager
      loop: "{{ where_used_details.meta.response_data[0].data.list | default([]) }}"
      # On s'assure de ne cibler que les politiques (conformément au step 4.1 de ton algo)
      when: 
        - item.type == 'policy'
      ignore_errors: true

    # ==========================================
    # 5) ON COMMIT
    # ==========================================
    - name: "[{{ current_adom }}] Commit des modifications du Workspace"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_commit:
        adom: "{{ current_adom }}"

    # ==========================================
    # 6) ON INSTALL LE POLICY PACKAGE
    # ==========================================
    # Décommenter et adapter si tu souhaites pousser la conf automatiquement aux Firewalls
    # - name: "[{{ current_adom }}] Installer le Policy Package"
    #   fortinet.fortimanager.fmgr_securityconsole_install_package:
    #     securityconsole_install_package:
    #       adom: "{{ current_adom }}"
    #       pkg: "Le_Nom_De_Ton_Package"

  always:
    # ==========================================
    # 7) ON UNLOCK L'ADOM
    # ==========================================
    - name: "[{{ current_adom }}] Déverrouiller l'ADOM"
      fortinet.fortimanager.fmgr_dvmdb_adom_workspace_unlock:
        adom: "{{ current_adom }}"

```

### 💡 Rappel pour l'étape 4.1 (Parsing du `Where Used`) :

Dans la boucle d'Ansible (`loop`), la structure exacte de `item.pkg` et `item.policyid` dépend de la façon dont le FortiManager formate la liste dans le call `4 Where used detail.bru`. Si le FortiManager renvoie des clés légèrement différentes (par exemple `pkg_name` à la place de `pkg`), il te suffira d'ajuster les variables dans la section `loop` pour coller à la réponse de ton API.

Tu es paré pour tester ton nettoyage global ! Prêt à l'exécuter sur ton premier ADOM de test ?
