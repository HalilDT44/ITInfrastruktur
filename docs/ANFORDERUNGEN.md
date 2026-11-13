# Nachweisplan zur Bewertung

Die Kriterien aus `bewertungskriterien.md` und `README (6).md` sind gemeinsam umgesetzt. Eine Konfiguration ist noch kein gemessener Verfügbarkeits- oder Leistungsnachweis. Verifizierte Ergebnisse stehen in `docs/PRUEFUNG.md`.

| Kriteriengruppe | Umsetzung / Abgabe | Noch am Zielcluster nachzuweisen |
|---|---|---|
| Drei Schichten, Bedienung, API, Health | Web, FastAPI, PostgreSQL; README; `/api/submissions`, `/api/health` | URL/DNS der Projektgruppe |
| Initialisierung, Persistenz | Automatische DDL; PostgreSQL StatefulSet; PVC | Pod löschen und Daten erneut lesen |
| Deployments, Limits, Labels, Namespace | `k8s/stack.yaml`, Generator | serverseitige Validierung |
| Externalisierung, Secrets | ConfigMaps; Setup generiert Secrets; Dateien statt Passwort-Env | Registry-Zugriff, lokale Secrets sicher aufbewahren |
| Reproduzierbarkeit | `scripts/setup.py --kubernetes` | auf Gruppencluster ausführen |
| Elf Lastfälle + Dauertest | `tests/load.js`, `scripts/load-matrix.ps1` | komplette Matrix mit 1000 parallelen 5-MiB-Bodies (5 GiB Transfer) |
| Langlaufender Endpunkt | `POST /api/reports/generate`, 2 s asynchrone Simulation, echtes PDF | p50/p95/p99 und Durchsatz mit 1 vs. 3 Replicas |
| Frontendausfall, Backend-/DB-Ausfall | 2 Replikate, Probes, UI-Fehlerbanner, Alerts | Fehlerexperimente und Alertzustellung |
| Scale-Out, Update, Rollback | HPA; maxUnavailable 0; Graceful Shutdown; README | Lasttest während Image-Wechsel; keine verlorenen Requests messen |
| Monitoring | Prometheus, Grafana, Alertmanager, kube-state-metrics Deployments | Kubelet-/Traefik-Scrapes, Dashboard, Restart-Alarm |
| Benachrichtigungen | interner unabhängiger Webhook-Empfänger; externer Webhook optional im Secret | externer Empfänger noch festzulegen; interne Zustellung in Logs prüfen |
| Isolation, TLS, Non-Root | Ingress TLS Secret, Default-Deny, DB nur API/Backup, Egress-Regeln | CNI muss NetworkPolicies erzwingen; HTTPS und verbotene Verbindungen testen |
| Read-only/Capabilities/Ports | App und Monitoring read-only; drop ALL; nur Ingress öffentlich | WAF benötigt schreibbare Konfigurationspfade; Ausnahme dokumentiert |
| WAF | OWASP ModSecurity CRS vor dem Webserver | Angriffsmuster → 403, legitime 5-MiB-Requests → 200 |
| Scan ohne Critical | `scripts/scan.ps1`, JSON-Reports | keine Erfolgsaussage ohne aktuellen Scanbericht |
| Automatisches Backup | CronJob alle 6 Stunden; Backup-PVC; 7 Tage Rotation | Restore-Probe; externes Backup für Node-/Clusterverlust ergänzen |

Die Datenbank ist persistent, aber nicht hochverfügbar. Der Ausfall ihrer einzigen Instanz wird erkannt und der Dienst neu gestartet; währenddessen meldet die UI einen Fehler. Dies entspricht den verlangten DB-Ausfallmaßnahmen, ersetzt aber kein PostgreSQL-HA-Cluster.
