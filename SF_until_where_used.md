C’est une excellente remarque, et tu as tout à fait raison ! C'est un point que j'aurais dû expliciter dans la structure.

La mécanique du **Where Used** dans l'API FortiManager est asynchrone :

1. Le premier appel (`/cache/search/where/used/start`) demande au FortiManager de lancer un calcul en tâche de fond et te donne un `token`.
2. Le second appel (`/cache/search/where/used/get/detail`) interroge le FortiManager pour récupérer le résultat.

Si l'ADOM est volumineux, le calcul prend du temps. Si Ansible exécute la tâche de lecture immédiatement après le démarrage, le FortiManager répondra qu'il est encore en train de calculer (généralement avec un champ `percentage` inférieur à 100 ou une liste vide).

L'utilisation des mots-clés **`until`**, **`retries`**, et **`delay`** d'Ansible est la solution parfaite pour gérer cette attente de manière propre (on appelle ça du *polling*).

Voici comment modifier la tâche de récupération dans ton fichier **`tasks/delete_item.yml`** :

```yaml
# ==========================================
# 3) RÉCUPÉRATION DES "none" POUR CET OBJET (Avec Polling)
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

- name: "[{{ suppression_flux_adom_targeted }}] Récupérer les détails du 'Where used' (Attente de la fin du calcul)"
  fortinet.fortimanager.fmgr_generic:
    method: "exec"
    params:
      - url: "/cache/search/where/used/get/detail"
        token: "{{ where_used_start.meta.response_data[0].data.token }}"
  register: where_used_details
  # --- LOGIQUE DE RETRY ---
  # On boucle jusqu'à ce que le calcul soit terminé (percentage == 100)
  # Si 'percentage' n'est pas retourné, on s'assure au moins que la structure data existe
  until: 
    - where_used_details.meta.response_data[0].data.percentage is not defined or 
      where_used_details.meta.response_data[0].data.percentage == 100
  retries: 10   # Nombre maximal d'essais
  delay: 3      # Temps d'attente en secondes entre chaque essai (Total max : 30 secondes)

```

### 💡 Pourquoi c'est indispensable dans ton cas ?

* **Évite les faux négatifs :** Sans le `until`, Ansible lirait une liste vide car le FortiManager n'aurait pas fini de chercher. Ton playbook penserait alors qu'aucune politique n'utilise l'objet `none` et passerait à la suite sans rien supprimer.
* **Optimisation du temps :** Si le FortiManager répond instantanément (en moins d'une seconde), Ansible n'attend pas et passe immédiatement à la suite. S'il met du temps, il retentera s'en bloquer toutes les 3 secondes.

Avec cet ajout, ton rôle est désormais paré pour les ADOM de production les plus lourds !
