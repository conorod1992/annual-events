# Annual Events

Annual Events is a Home Assistant custom integration for dates that come around every year, such as birthdays, anniversaries, pet birthdays, memorials, holidays, work anniversaries, name days, and your own custom events.

You manage your events from a dedicated **Annual Events** page in Home Assistant. The integration can also show events on a calendar, create sensors for automations and dashboards, and fire Home Assistant events that you can use for reminders.

Everything is stored locally in Home Assistant. Annual Events does not require an account, API key, cloud service, or internet connection.

> **Requirements**
>
> - Home Assistant **2026.7 or newer**
> - HACS is recommended for installation, but manual installation is also supported.
> - Optional LLM tools require Home Assistant **2026.8 or newer**.

## What you can do

With Annual Events you can:

- add birthdays, anniversaries, memorials, holidays, pet birthdays, work anniversaries, name days, and custom yearly dates;
- optionally add the original year, so Home Assistant can calculate ages or anniversary numbers;
- mark events as important;
- search, sort, and filter your events from the sidebar;
- show enabled events on a Home Assistant calendar;
- see the next event, next important event, and number of upcoming events as sensors;
- optionally create a separate sensor for an individual event;
- choose how 29 February events should behave in non-leap years;
- fire Home Assistant events a set number of days before each date and/or on the date itself;
- use Home Assistant actions to create, update, delete, search, and query events;
- ask supported LLM-based Home Assistant assistants about your annual events.

Annual Events stores its data locally and makes no network requests of its own.

## Installation

### HACS

Annual Events is a custom repository, so you need to add its GitHub repository to HACS before it will appear in the HACS integration list.

1. Open **HACS** in Home Assistant.
2. Open the HACS menu and choose **Custom repositories**.
3. Enter:

   `https://github.com/conorod1992/annual-events`

4. Choose **Integration** as the repository type.
5. Add the repository.
6. Find **Annual Events** in HACS and install it.
7. Restart Home Assistant.

You do **not** need to add a Lovelace resource or install a separate frontend.

### Manual installation

1. Download or clone this repository.
2. Copy the `annual_events` folder from `custom_components` into your Home Assistant `custom_components` directory.

Your final folder should look like:

```text
config/
└── custom_components/
    └── annual_events/
        ├── __init__.py
        ├── manifest.json
        └── ...
```

3. Restart Home Assistant.

## Set up Annual Events

After installing and restarting Home Assistant:

1. Go to **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **Annual Events**.
4. Complete the setup.

Annual Events uses one integration entry for your whole collection of yearly events, so you only need to add the integration once.

After setup, open **Annual Events** from the Home Assistant sidebar.

## Adding and managing events

The Annual Events sidebar page is the main place to manage your dates.

From there you can:

- add new events;
- edit or delete existing events;
- enable or disable events;
- mark events as important;
- choose whether an event should have its own sensor;
- search by name, alias, category, or notes;
- filter and sort the list.

The built-in categories are:

- Birthday
- Anniversary
- Pet
- Memorial
- Holiday
- Work
- Name day
- Custom

Only Home Assistant administrators can create, change, or delete events. Other users can view the collection.

### Original year

The **Original year** is optional.

For example:

- if you add `7 August` without a year, Annual Events can still tell you when the next occurrence is;
- if you add `7 August 2000`, it can also calculate the age or anniversary number for later years.

Annual Events does not guess a year when one has not been provided.

## Settings

Go to:

**Settings → Devices & services → Annual Events → Configure**

You can change the following options.

### Leap-day handling

For events on **29 February**, choose what should happen in years that do not have a 29 February:

- **Observe on 28 February** — default
- **Observe on 1 March**
- **Only in leap years**

The same choice is used throughout the integration, including the panel, sensors, calendar, actions, and LLM tools.

### Upcoming count period

Choose how many days ahead the **Upcoming annual events** sensor should count.

The default is **30 days**.

### Show Annual Events in the sidebar

Turn the dedicated sidebar page on or off.

Hiding the sidebar item does not delete your events or disable the integration.

### Advance notice

Choose how many days before an annual event Home Assistant should fire an `annual_events_occurrence` event.

The default is **7 days**.

This does not send a notification by itself. It gives your Home Assistant automations an event they can react to.

### Trigger time

Choose the local time when Annual Events performs its daily occurrence check.

The default is **09:00**.

### Day-of events

When enabled, Annual Events also fires an `annual_events_occurrence` event on the day of the annual event.

This is enabled by default.

## Home Assistant entities

Annual Events creates several entities automatically.

| Entity | What it shows |
| --- | --- |
| `sensor.next_annual_event` | Date of the next enabled annual event |
| `sensor.next_important_annual_event` | Date of the next enabled event marked important |
| `sensor.next_annual_event_name` | Name of the next enabled annual event |
| `sensor.next_important_annual_event_name` | Name of the next enabled important event |
| `sensor.upcoming_annual_events` | Number of events within the configured upcoming period |
| `calendar.annual_events` | Enabled annual events as all-day calendar entries |

The date and name sensors also include useful attributes such as the event name, date, category, number of days remaining, importance, and occurrence number where available.

For example:

```jinja
{{ states('sensor.next_annual_event_name') }}
```

returns the name of the next event.

To get its date:

```jinja
{{ state_attr('sensor.next_annual_event_name', 'occurrence_date') }}
```

### Individual event sensors

When editing an event, turn on **Expose individual sensor** if you want that event to have its own date sensor.

This can be useful for dashboards or automations that refer to one specific birthday or anniversary.

The sensor keeps the same internal identity if you later rename the event.

If the event is disabled, its individual sensor is not loaded until the event is enabled again.

## Calendar

`calendar.annual_events` shows enabled annual events as all-day calendar entries.

Because these are recurring yearly dates, Annual Events calculates the actual occurrence for each year rather than storing one fixed future date.

The calendar follows your configured leap-day policy.

## Reminder automations

Annual Events can fire a Home Assistant event:

```text
annual_events_occurrence
```

This can happen:

- a configured number of days before an annual event; and
- on the date itself, if day-of events are enabled.

This is often the easiest way to build notifications because Annual Events handles the yearly date calculation for you.

### Example: notify in advance

This example sends a notification when an event reaches the configured advance-notice date:

```yaml
alias: Annual event advance reminder
triggers:
  - trigger: event
    event_type: annual_events_occurrence
    event_data:
      trigger: advance

actions:
  - action: notify.notify
    data:
      title: Annual event reminder
      message: >-
        {{ trigger.event.data.name }} is in
        {{ trigger.event.data.days_until }} days.
```

The event data includes information such as:

```yaml
event_id: 4df57b76-1f7b-4b6c-80cb-04abb8b8a719
name: Example birthday
category: birthday
occurrence_date: "2026-09-14"
occurrence_number: 30
important: true
trigger: advance
days_until: 7
advance_days: 7
```

On the day itself, `trigger` is `today` and `days_until` is `0`.

Annual Events remembers occurrence events it has already fired, so restarting Home Assistant should not cause the same reminder to be fired repeatedly. If Home Assistant starts after the configured trigger time, Annual Events also performs a catch-up check for work that was missed while Home Assistant was offline.

## Actions

> This section is mainly for automations, scripts, templates, and more advanced Home Assistant setups. You do not need to use these actions just to manage annual events from the sidebar.

Annual Events provides these Home Assistant actions:

- `annual_events.create_event`
- `annual_events.update_event`
- `annual_events.delete_event`
- `annual_events.search`
- `annual_events.get_upcoming`
- `annual_events.get_between`
- `annual_events.get_next`
- `annual_events.get_for_date`

The query actions return response data, which means their results can be stored in a `response_variable` and used later in the same script or automation.

### Create an event

You can create events from the Home Assistant automation or script editor.

For example, in **Edit in YAML**:

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

### Get upcoming events

```yaml
action: annual_events.get_upcoming
data:
  days: 30
  limit: 10
response_variable: upcoming_events
```

The results are available in:

```jinja
{{ upcoming_events.occurrences }}
```

### Get events between two dates

```yaml
action: annual_events.get_between
data:
  start: "2026-12-01"
  end: "2027-01-10"
  important_only: true
  limit: 100
response_variable: annual_events_result
```

A response looks like:

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

### Get the next event

```yaml
action: annual_events.get_next
data:
  category: birthday
  important_only: true
response_variable: next_event
```

The result is available as:

```jinja
{{ next_event.event }}
```

If no matching event exists, `next_event.event` is `null`.

### Get events for one date

```yaml
action: annual_events.get_for_date
data:
  date: "2026-09-14"
  important_only: false
response_variable: events_on_date
```

The response contains a `count` and an `occurrences` list.

### Updating and deleting events

Updates and deletions use the event's unique `event_id`, rather than its name.

This avoids accidentally changing the wrong event when two events have the same or similar names.

You can find an event ID in places such as:

- the Annual Events panel;
- search action results;
- query action results;
- sensor attributes.

## More automation examples

### Notify when the next important event is seven days away

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
        {{ state_attr('sensor.next_important_annual_event', 'name') }}
        is in seven days.
```

If you only need your configured Annual Events advance notice, the event-triggered example earlier in this README is normally simpler because you do not need to create a separate daily time check.

### Notify on the day of an individually exposed event

Replace the entity ID below with your own individual event sensor:

```yaml
alias: Birthday this morning
triggers:
  - trigger: time
    at: "08:00:00"

conditions:
  - condition: template
    value_template: >-
      {{ states('sensor.mums_birthday') == now().date().isoformat() }}

actions:
  - action: notify.notify
    data:
      message: "Mum's birthday is today."
```

### Announce the next event

Replace the TTS and media-player entities with your own:

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
        The next annual event is {{ event.name }}
        on {{ event.occurrence_date }}.
```

## Voice and LLM access

On Home Assistant versions that support integration-provided LLM tools, Annual Events provides read-only tools that allow a compatible assistant to look up your events.

Examples of questions include:

- "When is Mum's birthday?"
- "How old will Mum be on her next birthday?"
- "What important events are coming up?"
- "What events are between 1 December and 10 January?"

Names and aliases can both be used when searching.

If you did not provide an original year, Annual Events will not guess an age or anniversary number.

### Available LLM tools

- `search_annual_events`
- `get_upcoming_annual_events`
- `get_annual_events_between`

These tools are read-only. An LLM cannot create, edit, or delete annual events through them.

LLM tools require Home Assistant **2026.8 or newer**. The rest of Annual Events works on Home Assistant **2026.7 or newer**.

## How dates are calculated

Annual Events stores the month and day for every event. The original year is optional.

All calculations use the timezone configured in Home Assistant.

Date-range queries include both the start and end date and can cross New Year.

For an event with an original year, the original date is treated as occurrence number `0`.

For example, an event beginning on 7 August 2000 has:

- occurrence `0` in 2000;
- occurrence `1` in 2001;
- occurrence `26` in 2026.

For birthdays, the occurrence number therefore matches the person's age on that birthday.

## Privacy and storage

Annual Events is designed to keep its data inside Home Assistant.

- It makes no network requests.
- It includes no analytics or telemetry.
- Event records are stored in Home Assistant's `.storage` directory.
- Home Assistant backups normally include this data.
- Diagnostics do not include event names, aliases, notes, exact dates, or original years.

The main event data is stored under:

```text
.storage/annual_events.events
```

Annual Events also stores a small delivery record so that advance/day-of events are not repeatedly fired after restarts.

Do not manually edit Annual Events files in `.storage` while Home Assistant is running.

If the stored event data cannot be read, Annual Events fails setup rather than silently replacing the collection with an empty one.

## Troubleshooting

### Annual Events is missing from the sidebar

Check that **Show Annual Events in the sidebar** is enabled under the integration's **Configure** options.

If it is enabled, try:

1. reloading the integration; and
2. refreshing or hard-refreshing the Home Assistant browser/app view.

### An individual event sensor is missing

The event must have both:

- **Enabled** turned on; and
- **Expose individual sensor** turned on.

### Age or anniversary number is missing

Add the real **Original year** to the event.

If the year is unknown, Annual Events intentionally leaves the age or anniversary number blank rather than guessing.

### A 29 February event appears on an unexpected date

Check **Leap-day handling** under the integration's **Configure** options.

### An update or delete action says the event ID is unknown

Update and delete actions require the event's exact `event_id`.

You can retrieve it from the panel, an action response, a search result, or relevant sensor attributes.

### Setup fails after storage damage

Restore `.storage/annual_events.events` from a Home Assistant backup.

Annual Events deliberately does not overwrite unreadable stored data with an empty collection.

## Advanced technical information

The Annual Events frontend communicates with the integration through authenticated Home Assistant WebSocket commands.

Read operations are available to authenticated users. Create, update, and delete operations are checked on the backend and require a Home Assistant administrator account.

The WebSocket command namespace is `annual_events/` and includes:

- `list`
- `get`
- `create`
- `update`
- `delete`
- `search`
- `upcoming`
- `between`
- `settings`

Range and result sizes are bounded to protect Home Assistant from accidentally expensive requests. The `between` command is limited to 3,660 days and 5,000 results.

Individual event sensors use the event's stable internal ID, so renaming an event does not create a new entity identity.

## Development

The current Home Assistant development stack for this repository uses Python 3.14.

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

The frontend is checked into the repository and does not require a Node.js build.

CI also runs Home Assistant hassfest and HACS repository validation.

## Current limitations

- English is currently the only included translation.
- LLM access is read-only.
- JSON, CSV, ICS, and vCard import/export are not currently included.
- External holiday providers and country holiday APIs are not included.
- Screenshots are not yet available.

Possible future improvements include import/export, additional translations, bulk editing, other import formats, and carefully permissioned write tools for LLM integrations.

## License

MIT. See [LICENSE](LICENSE).
