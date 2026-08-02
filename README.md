# Annual Events

Annual Events is a local-first Home Assistant custom integration for birthdays, anniversaries, pet birthdays, memorials, work anniversaries, holidays, name days, and custom yearly dates.

It keeps one collection-level config entry. Each annual event is an internal record—not a helper or another config entry—and can optionally be projected as its own sensor. Rich results travel through WebSocket commands, action responses, the calendar entity, and supported LLM tools rather than being squeezed into entity state strings.

## Features

- UI-only, credential-free setup with one config entry
- Responsive sidebar management page for list, add, edit, delete, search, sort, filter, and quick toggles
- Optional original year with correct age/anniversary numbers
- Configurable 29 February handling
- Versioned local storage and concurrency-safe mutations
- Deterministic name, alias, category, and notes search
- Aggregate next-event, next-important-event, and upcoming-count sensors
- Optional stable-ID sensor for each enabled event
- All-day calendar with expanded occurrences across years
- Structured query and mutation actions
- Authenticated WebSocket API with administrator-only mutations
- Read-only LLM tools on Home Assistant versions that support contributed integration tools
- Privacy-redacted diagnostics; no telemetry or network requests

Annual Events requires Home Assistant 2026.7 or newer. Contributed read-only LLM tools require Home Assistant 2026.8 or newer; the rest of the integration remains available on 2026.7.

## Screenshots

Screenshots have not yet been captured for this first release. The checked-in panel is complete and build-free.

## Installation

### HACS custom repository

1. Open HACS.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/conorod1992/annual-events` as an **Integration**.
4. Install **Annual Events** and restart Home Assistant.

No separate Lovelace resource or frontend build is required.

### Manual

Copy `custom_components/annual_events` into the `custom_components` directory under your Home Assistant configuration directory, then restart Home Assistant.

## Setup and management

Go to **Settings → Devices & services → Add integration**, search for **Annual Events**, and confirm setup. Only one Annual Events collection can be configured.

Open **Annual Events** in the sidebar. The page supports desktop and mobile layouts, keyboard-usable controls, loading/error/empty states, search, category and status filters, important-only filtering, sorting by name or next occurrence, and confirmation before deletion. Non-administrators can read the collection; the backend permits create, update, and delete operations only to administrators through the panel API.

Use the integration's **Configure** button to choose:

- the leap-day policy;
- the period used by the upcoming count sensor;
- whether the sidebar panel is shown.

Individual events are always managed from the dedicated panel or actions, never from the options flow.

## Dates, years, and occurrence numbers

Month and day are required. The original year is optional and is stored as a real optional component—Annual Events never invents a placeholder year.

When the year is absent, next occurrence and days remaining still work, while age/anniversary number is omitted. When it is present, the original date is occurrence **zero**: a birth or wedding on 7 August 2000 has occurrence 0 in 2000 and occurrence 26 in 2026.

Calculations use Home Assistant's configured local timezone. Range queries are inclusive at both ends, can cross New Year, and can return the same record once per covered year.

### Leap-day policy

For an event recorded on 29 February, choose one collection-wide policy:

- observe it on 28 February in non-leap years (default);
- observe it on 1 March in non-leap years;
- return it only in leap years.

The selected policy is shared by the panel, sensors, calendar, actions, WebSocket queries, and LLM tools.

## Entities

The integration creates:

- `sensor.next_annual_event`: ISO date state plus bounded metadata for the next enabled event;
- `sensor.next_important_annual_event`: the same projection for important enabled events;
- `sensor.upcoming_annual_events`: numeric count in the configured period;
- `calendar.annual_events`: enabled records as concrete all-day occurrences.

Turning on **Expose individual sensor** creates a date sensor with a unique ID based on the immutable event ID. Renaming an event does not create a new entity. Turning exposure off removes it from runtime while retaining its entity-registry identity for a future re-enable; deleting the record removes the orphaned registry entry.

No sensor contains an unbounded event list.

## Actions

Available actions are:

- `annual_events.create_event`
- `annual_events.update_event`
- `annual_events.delete_event`
- `annual_events.search`
- `annual_events.get_upcoming`
- `annual_events.get_between`

Update and delete require the exact stable event ID. Query actions always return structured response data. Mutation actions optionally return the affected record when the caller requests a response.

Create an event in the automation UI's **Edit in YAML** editor:

```yaml
action: annual_events.create_event
data:
  name: John's birthday
  month: 8
  day: 7
  category: birthday
  aliases:
    - John
  important: true
  enabled: true
  expose_entity: true
response_variable: created_event
```

Query with a response variable:

```yaml
action: annual_events.get_between
data:
  start: "2026-12-01"
  end: "2027-01-10"
  important_only: true
  limit: 100
response_variable: annual_events_result
```

The response has this shape:

```yaml
count: 2
occurrences:
  - event_id: 4df57b76-1f7b-4b6c-80cb-04abb8b8a719
    name: Example birthday
    category: birthday
    occurrence_date: "2026-12-14"
    occurrence_number: 30
    important: true
    days_until: 42
```

### Automation examples

Notify seven days before the next important event:

```yaml
alias: Important annual event in seven days
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: template
    value_template: >-
      {{ state_attr('sensor.next_important_annual_event', 'days_until') == 7 }}
actions:
  - action: notify.notify
    data:
      title: Annual event reminder
      message: >-
        {{ state_attr('sensor.next_important_annual_event', 'name') }} is in seven days.
```

Notify on the morning of a birthday exposed as an individual sensor (replace the entity ID):

```yaml
alias: Birthday this morning
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: template
    value_template: "{{ states('sensor.mums_birthday') == now().date().isoformat() }}"
actions:
  - action: notify.notify
    data:
      message: "Mum's birthday is today."
```

Query and announce the next event (replace the TTS target entities):

```yaml
sequence:
  - action: annual_events.get_upcoming
    data:
      days: 366
      limit: 1
    response_variable: next_events
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.kitchen
      message: >-
        {% set event = next_events.occurrences[0] %}
        The next annual event is {{ event.name }} on {{ event.occurrence_date }}.
```

## Voice and LLM access

On Home Assistant releases supporting contributed `llm.py` tools, Annual Events supplies three read-only tools:

- `search_annual_events`
- `get_upcoming_annual_events`
- `get_annual_events_between`

They support questions such as “When is Mum's birthday?”, “How old will Mum be on her next birthday?”, and “What important events occur between 1 December and 10 January?” Names and aliases are searched deterministically. A missing original year returns no occurrence number rather than a guessed age.

Write tools are deliberately not exposed in this release. Creating, changing, or deleting data through a model introduces permission and ambiguity risks; use the administrator-protected panel or exact-ID actions instead. Non-LLM Assist custom intents are not included.

## Privacy, storage, and backup

Annual Events makes no network requests and contains no analytics or telemetry. Records are stored locally using Home Assistant's versioned storage under `.storage/annual_events.events`. Normal logs never include whole personal records, and diagnostics contain counts, categories, schema/version information, and options only—not names, aliases, notes, exact dates, or original years.

Home Assistant's normal backups include `.storage`. Take a backup before large imports or upgrades and do not edit storage files while Home Assistant is running. If storage cannot be loaded, setup fails without replacing it with an empty collection.

## WebSocket API

The frontend uses authenticated commands under `annual_events/`: `list`, `get`, `create`, `update`, `delete`, `search`, `upcoming`, `between`, and `settings`. Read commands accept bounded filters and limits. Mutation commands enforce administrator status in Python, regardless of what controls the browser displays. `between` is capped at 3,660 days and 5,000 results.

## Troubleshooting

- **Panel missing:** confirm **Show Annual Events in the sidebar** is enabled, reload the integration, and hard-refresh the browser.
- **Individual sensor missing:** both **Enabled** and **Expose individual sensor** must be on for that event.
- **Age is absent:** add the real original year. This is intentional when it is unknown.
- **Unexpected leap-day date:** review the integration's leap-day option.
- **Action says unknown ID:** retrieve the stable ID from the panel, search response, sensor attributes, or `annual_events.search`; names are never accepted for deletion.
- **Setup fails after storage damage:** restore `.storage/annual_events.events` from a Home Assistant backup. The integration will not silently overwrite unreadable data.

## Development

Use Python 3.14 for the current Home Assistant development stack:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
ruff format --check .
ruff check .
mypy custom_components/annual_events
pytest --cov=custom_components.annual_events
```

The frontend is a checked-in, dependency-free web component; no Node.js build is needed. CI also runs hassfest and HACS repository validation.

## Current limitations and roadmap

- English is the only included translation.
- LLM access is read-only and depends on the Home Assistant contributed-tool platform.
- JSON/CSV/ICS/vCard import and export are not included yet.
- Country holiday sources and external holiday APIs are intentionally absent.
- Screenshots are not yet available.

Planned work includes versioned JSON import/export with validation and duplicate policies, additional translations, bulk editing, optional import formats, and safe write tools if Home Assistant exposes a sufficiently clear permission and confirmation model.

## License

MIT. See [LICENSE](LICENSE).
