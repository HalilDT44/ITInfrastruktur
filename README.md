# Zendo – Projektverwaltung

Web-App ohne Anmeldung und ohne Build-Schritt, angelehnt an die bereitgestellte Designvorlage.

## Starten

### Mit Docker (empfohlen)

Docker Desktop starten und im Projektordner ausführen:

```powershell
docker compose up -d --build
```

Anschließend **http://localhost:8080** öffnen.

```powershell
# Status und Healthcheck anzeigen
docker compose ps

# Logs anzeigen
docker compose logs -f

# Anwendung stoppen und Container entfernen
docker compose down
```

Nach Änderungen am Quellcode erneut `docker compose up -d --build` ausführen.
Ist Port 8080 bereits belegt, lässt er sich in PowerShell ändern:

```powershell
$env:ZENDO_PORT = "8081"
docker compose up -d --build
```

Die Anwendung ist dann unter http://localhost:8081 erreichbar. Der Port ist nur auf dem lokalen Rechner freigegeben. Der Container liefert die Anwendung mit Nginx aus; Projekte und Aufgaben bleiben im Browser gespeichert. Dafür ist kein Docker-Volume erforderlich. Beim Wechsel des Ports verwendet der Browser einen eigenen Datenspeicher; vorhandene Daten bleiben unter der bisherigen Adresse erreichbar. Ein Container-Neustart oder Neubau löscht die Browserdaten nicht.

### Ohne Docker

Im Projektordner ausführen:

```powershell
python -m http.server 8080
```

Danach http://localhost:8080 öffnen. Alternativ lässt sich `index.html` direkt öffnen; für einen stabilen lokalen Browser-Speicher wird der lokale Webserver empfohlen.

## Funktionen

- Dashboard mit Projektfortschritt und anstehenden Aufgaben
- Projekte erstellen, bearbeiten und mit ihren Aufgaben löschen
- Aufgaben mit Beschreibung, Status, Priorität, Kategorie, Verantwortlichem, Fälligkeit und Teilaufgaben
- Kanban mit Drag-and-drop sowie Listenansicht; Status auch im Aufgabendialog änderbar (Mobilgeräte/Tastatur)
- Suche, Prioritätsfilter und Sortierung
- Projektberichte mit Projekt- und Fälligkeitsfiltern, Kennzahlen und Aufgabentabelle
- PDF: Unter **Berichte & PDF → Als PDF speichern** im Browser-Druckdialog **Als PDF speichern** wählen. Das Drucklayout ist für A4 quer optimiert.
- Automatische Speicherung im Local Storage des verwendeten Browsers

Beim ersten Start werden bearbeitbare Beispieldaten angelegt. Leere Projekte sind ebenfalls möglich. Alle Inhalte sind auf Deutsch, es werden keine Backend-Dienste benötigt. Die optionalen Google Fonts werden bei fehlender Verbindung durch Systemschriften ersetzt.

## Datenspeicherung

Dies ist eine lokale Einzelplatzanwendung. Daten bleiben im Browserprofil und werden weder auf einem Server gespeichert noch zwischen Geräten synchronisiert. Browserdaten löschen entfernt auch die Projekte. Es gibt noch keine Benutzerverwaltung, Zusammenarbeit oder Datensicherung. Persönliche Daten werden von der Anwendung nicht an einen Server übertragen; beim Laden der optionalen Google Fonts entsteht eine Anfrage an Google.

## Prüfung

JavaScript-Syntax prüfen: `node --check app.js`.
