# Verifizierte Prüfergebnisse

Stand: 14.11.2026. Lokaler, isolierter k3d-Cluster `zendo-validation`, k3s v1.35.5+k3s1, ein Server und ein Agent, Docker Desktop mit 8 CPUs und 7,648 GiB RAM. Die Ergebnisse gelten für diese Umgebung; auf dem Gruppencluster ist eine erneute Abnahme erforderlich.

## Bestandene Prüfungen

| Prüfung | Tatsächliches Ergebnis | Nachweis unter docs/evidence |
|---|---|---|
| Docker und Kubernetes Start | Web/API/DB und Monitoring bereit; Ressourcen serverseitig angewandt | scrape-targets.json |
| Web: 10/0 s, 100/1 s, 1000/5 s | jeweils alle HTTP 200 | web-10.json, web-100.json, web-1000-5.json |
| Web: 1000/1 s | 1000 HTTP 200 | web-1000-1.json |
| Web: 1000/min über 10 min | 10001 Requests, 0 Fehler, 0 ausgelassene Iterationen; p95 30,75 ms | soak.json |
| API normale Bodies: 10/0 s, 100/1 s, 1000/5 s | jeweils alle HTTP 200 | api-10.json, api-100.json, api-1000.json |
| API 5 MiB: 10/0 s | alle HTTP 200 | large-10.json |
| API 5 MiB: 100/1 s | 100/100 korrekt, SHA-256 geprüft; p95 12,49 s | large-100.json |
| API 5 MiB: 1000/5 s | 1000/1000 korrekt, SHA-256 geprüft; p50 54,66 s, p95 62,38 s, p99 63,84 s | large-1000.json |
| Berichte: 1 vs. 3 API-Replikate | 1,94 vs. 5,16 erfolgreiche PDFs/s (Faktor 2,65) | report-1.json, report-3.json |
| Berichtslatenz p50/p95/p99, 1 Replikat | 2031 / 2253 / 2323 ms | report-1.json |
| Berichtslatenz p50/p95/p99, 3 Replikate | 2015 / 2101 / 2321 ms | report-3.json |
| API-Ausfall / DB-Ausfall | Health 502 / 503; Webseite weiterhin 200; beide Alarme zugestellt | resilience.json, notifications.log |
| DB-Persistenz | Workspace unverändert nach DB-Pod-Neustart | resilience.json |
| Frontend-Pod gelöscht | 125 Anfragen, 0 Fehler | resilience.json |
| Backend-Imagewechsel + Rollback | 144 PDF-Anfragen, 0 Fehler; Update auf 1.0.1 und Undo | rolling-update.json |
| Automatisches Backup und Restore | CronJob manuell ausgelöst; Dump erfolgreich in separate DB eingespielt | restore.log |
| Unberechtigter DB-Zugriff | Verbindung aus unberechtigtem Job gesperrt; Backup/Restore-Verbindung erlaubt | network-denial.log, restore.log |
| HPA Scale-Out | WAF skalierte unter Last von 2 auf 8; API/Web ebenfalls horizontal skaliert | hpa.json; Laufprotokolle artifacts |
| Monitoring-Scrapes | API-Pods, cAdvisor, kube-state-metrics, Traefik alle `up` | scrape-targets.json |
| Sicherheitsscan eigene Images | Trivy: 0 kritische Befunde in Web und API | scan-web.json, scan-api.json |
| HTTPS / WAF | selbstsigniertes Ingress-TLS; getestetes XSS-Muster → HTTP 403; legitimes PUT und Upload → 200 | Integrationstest und WAF-Konfiguration |
| Syntax und Ressourcen | node --check, Python compileall, validate_manifests.py, Integrationstest erfolgreich | reproduzierbare Tests im Repository |

## Bedingungen und behobene Engpässe

Die Lastfälle wurden einzeln abgenommen, nicht alle gleichzeitig. Der Zehn-Minuten-Webtest lief zusätzlich während der Ausfall-/Updateprüfungen. Die 1000 großen Uploads verwenden das **vorbereitete Lastprofil mit acht bereiten WAF-Replikaten** (`infrastructure/high-load.yaml`). Das erfüllt sowohl den Fall mit erlaubter 429-Ablehnung als auch den strengeren Fall mit ordnungsgemäßer Antwort; im erfolgreichen Großlastlauf war keine Ablehnung nötig.

Ein erster 1000er-Test mit je VU separat alloziertem 5-MiB-Body überforderte die lokale Docker-VM. Dieser Generator wurde für große Bodies durch `tests/large_load.py` ersetzt. Ein erster Lauf mit zwei kalten WAF-Pods führte zu OOM-Kills. Kubernetes startete die Container neu; die Restart-Alarme wurden zugestellt. HPA reagiert langsamer als ein fünfsekündiger Burst: Das große Lastprofil muss vorher bereitstehen. Die Infrastruktur ist daher nicht pauschal für unvorbereitete beliebig große Bursts garantiert.

Zusätzlich begrenzte der k3d-Loadbalancer Verbindungen auf 1024 pro Worker. Das lokale Setup hebt die Grenze auf 8192 an. Der erfolgreiche Web-1000/1-s-Lauf und die großen Linux-Streaming-Läufe greifen aus dem Docker-Netz auf denselben TLS-Ingress zu; sie umgehen ausschließlich das zusätzliche Windows-Portforwarding. API, WAF und TLS wurden dabei vollständig durchlaufen. Frühere Fehlversuche bleiben unter artifacts erhalten und werden nicht als bestanden gewertet.

Der erste Trivy-Scan fand CVE-2026-111497 in brotli-libs 1.2.0-r1 des Frontend-Basisimages. `apk upgrade --no-cache` installiert die behobene Version; der anschließende Scan meldete keine kritischen Schwachstellen. Die Berichte enthalten Image-Identitäten und Scanzeitpunkt. Keine Aussage über völlige Schwachstellenfreiheit oder künftige Datenbankstände.

Der Berichtsskalierungstest verwendet 16 VUs über 30 Sekunden bei vier Berichtsslots pro Pod. Kontrollierte 429-Antworten werden separat von erfolgreichen PDFs behandelt. Die Latenzquantile gelten ausschließlich für erfolgreiche Berichte; Erfolgsdurchsatz und Rohdaten sind ebenfalls enthalten.

## Verbleibende standortspezifische Abnahme

Die Container wurden lokal gebaut und geprüft. Für die Gruppenabgabe müssen sie in eine erreichbare Registry gepusht und DNS/Ingress-IP auf dem Gruppencluster zugeordnet werden. Der interne Webhook-Empfänger ist getestet; ein externer Alarmkanal benötigt eine von der Gruppe angegebene Zieladresse. Kein externer Empfänger wurde ohne Auftrag angeschrieben. Browserdarstellung und Fehlerbanner wurden im Code umgesetzt; eine automatisierte visuelle Browserprüfung wurde nicht durchgeführt. Node-/Clusterverlust des lokalen PV ist durch dieses Backup-PVC allein nicht abgesichert.
