# Plant Chat MVP Spec

Status: Draft  
Product: My Garden  
Last updated: 2026-05-01

## Goal

Give each plant its own persistent follow-up conversation so the user can ask questions after a diagnosis without losing context or reopening long, messy chat threads elsewhere.

The feature should feel like:

- "I can ask about this specific plant."
- "The app already remembers what happened last time."
- "I do not need to restate the diagnosis, photo, or recent history."

## Problem

Today, My Garden is good at:

- organizing plants
- saving photo-based diagnoses
- showing history over time

But there is still a gap right after a diagnosis:

- users often have follow-up questions
- those questions are about a specific plant, not the whole garden
- users want continuity with prior diagnoses
- generic ChatGPT threads become long, repetitive, and hard to scan

Examples:

- "Should I water today or wait one more day?"
- "What should I watch tomorrow?"
- "Does this need repotting now or later?"
- "Why did the AI say low humidity if the soil looks damp?"

## Core Product Decision

Use **one persistent chat thread per plant**.

Do not create:

- one global garden chatbot
- one separate thread per diagnosis
- multiple chat threads per plant in MVP

Rationale:

- users think in terms of a plant's ongoing story
- each diagnosis is part of that story, not a separate silo
- a single thread per plant keeps context strong and UX simple

## MVP Experience

### Entry Points

Add an `Ask follow-up` CTA in two places:

1. On the plant detail page, near `Latest read`
2. Inside expanded diagnosis history rows

### Routing

New route:

- `#/plant/:plantId/chat`

Optional anchored route:

- `#/plant/:plantId/chat?checkin=:checkinId`

The anchored route opens the same plant chat thread, but preloads one diagnosis as the active context for the next user message.

### Chat Screen

The plant chat screen should include:

- a back button to plant detail
- plant header: name, Chinese name, species, location
- optional pinned diagnosis context card when launched from a check-in
- message list
- composer
- 3 to 4 suggested question chips

Suggested chips:

- `Should I water today?`
- `What should I watch next?`
- `Does this need repotting?`
- `What if it gets worse?`

### Message Behavior

User messages should feel grounded in plant context automatically.

The assistant should:

- answer the question naturally
- refer to recent diagnosis history when useful
- avoid re-identifying the plant
- avoid contradicting recent evidence unless today's context clearly changes the situation

## UX Flow

### Flow A: Follow-up from latest diagnosis

1. User opens plant detail
2. User taps `Ask follow-up`
3. App opens `#/plant/:plantId/chat`
4. Latest diagnosis is pinned as context at the top
5. User asks a question
6. Assistant replies with plant-aware follow-up guidance

### Flow B: Follow-up from older diagnosis

1. User expands a past diagnosis in photo history
2. User taps `Ask follow-up about this diagnosis`
3. App opens `#/plant/:plantId/chat?checkin=:checkinId`
4. That diagnosis is pinned as the active context
5. User asks a question about that moment in time

### Flow C: Return to an existing plant chat

1. User opens plant detail
2. User taps `Plant chat`
3. App opens the same persistent thread with prior messages intact

## Screen Design

### Plant Detail Additions

Add:

- `Ask follow-up` text button near `Latest read`
- `Ask about this diagnosis` inside expanded history rows
- optional `Plant chat` primary CTA if there are already chat messages

Do not add a separate chat tab at the garden level in MVP.

### New Plant Chat Screen

Sections:

1. Header
2. Context card
3. Messages
4. Suggested prompts
5. Composer

Header content:

- plant name
- Chinese name if available
- species
- location

Context card content:

- diagnosis title
- diagnosis date
- diagnosis summary
- owner note if available

Composer behavior:

- text-only in MVP
- no new photo upload in the first version
- `Send` button disabled while pending

## Data Model

Add two new tables.

### `chat_threads`

Purpose: one persistent thread per plant

Suggested columns:

- `id TEXT PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `plant_id TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `rolling_summary TEXT`
- `open_questions_json TEXT`
- `last_advice_json TEXT`

Constraints:

- unique `(user_id, plant_id)` in MVP

Notes:

- `rolling_summary` is the key token-efficiency field. It stores a compact plant-chat memory so we do not need to replay the full thread on every turn.
- `open_questions_json` can store unresolved user concerns for continuity.
- `last_advice_json` can store the last structured follow-up guidance we gave, so the assistant can stay consistent without re-reading the whole transcript.

### `chat_messages`

Purpose: message history inside the plant thread

Suggested columns:

- `id TEXT PRIMARY KEY`
- `thread_id TEXT NOT NULL`
- `user_id TEXT NOT NULL`
- `plant_id TEXT NOT NULL`
- `checkin_id TEXT`
- `role TEXT NOT NULL`  
  Values: `user`, `assistant`
- `body TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `suggested_actions_json TEXT`
- `watch_signals_json TEXT`

Notes:

- `checkin_id` is nullable because some follow-up questions are about the plant overall, not one diagnosis
- `suggested_actions_json` and `watch_signals_json` are optional structured output from the assistant, even if the UI only shows plain text first

## Token Efficiency Principles

This feature should be designed as a **structured plant follow-up layer**, not a general-purpose chat transcript product.

Rules:

- never send the full plant history
- never send the full chat transcript
- never re-send images on every turn by default
- deterministically select context on the server
- summarize old context into memory instead of replaying it

The app should behave like:

- a small plant-specific memory system
- plus a lightweight follow-up answer layer

Not like:

- an ever-growing raw ChatGPT conversation clone

## API Shape

### `GET /api/plants/:plantId/chat`

Returns:

- `plant`
- `thread`
- `messages`
- optional `suggested_prompts`

If the thread does not exist yet, the server can lazily create it.

### `POST /api/plants/:plantId/chat/messages`

Request:

```json
{
  "body": "Should I water today?",
  "checkin_id": "optional-checkin-id"
}
```

Response:

```json
{
  "thread": { "...": "..." },
  "user_message": { "...": "..." },
  "assistant_message": {
    "id": "msg_...",
    "role": "assistant",
    "body": "I would wait until the top inch feels dry...",
    "suggested_actions": ["Check top inch tonight", "Water tomorrow morning if dry"],
    "watch_signals": ["crispy edges", "drooping by evening"]
  }
}
```

### Optional later endpoint

Not required for MVP:

- `DELETE /api/chat/messages/:id`

## AI Context Packet

Each assistant response should be grounded in plant-specific context assembled server-side.

### Always include

- plant name
- Chinese name
- species
- location
- latest diagnosis
- latest owner note
- recent 3 check-ins
- rolling plant chat summary

### Include only a shallow recent transcript

- last 4 to 6 chat turns max

This should mean:

- last 2 to 3 user messages
- last 2 to 3 assistant messages

Do not replay older chat once it has been absorbed into `rolling_summary`.

### Include when available

- focused `checkin_id` context if the message came from a diagnosis entry point
- focused diagnosis title, summary, owner note, and timestamp

### Image policy

Default: **text-only follow-up chat**.

Do not re-send a plant image on routine follow-up turns such as:

- `Should I water today?`
- `What should I watch tomorrow?`
- `Does this need repotting soon?`

Only include image context when:

- the user uploads a new photo in chat later
- the user explicitly asks for visual comparison
- the server determines the question cannot be answered well from saved structured context

### Current recommendation

For MVP, keep chat text-first after the diagnosis has already happened. The chat model should rely on:

- structured plant history
- latest diagnosis text
- recent user notes
- rolling chat summary

This keeps latency and cost lower than re-sending images on every follow-up turn.

### Recommended server-built context packet

For each follow-up request, assemble:

1. plant identity
2. latest diagnosis
3. latest owner note
4. last 3 check-ins
5. rolling chat summary
6. last 4 to 6 chat turns
7. optional focused check-in context

This packet should be built deterministically in server code, not selected by the model.

## Assistant Prompt Behavior

The plant chat assistant should:

- treat plant identity as fixed context
- not re-identify the plant
- answer in the user's preferred language if we have it
- be concise and actionable
- reference recent history when useful
- say when uncertainty is high

Good answer style:

- 1 to 3 short paragraphs or a few short bullets
- focus on what to do next
- avoid long generic plant-care explainers

The assistant should also assume:

- older thread context has already been summarized
- it should not restate large amounts of prior history unless the user asks

## Structured Output

Even if the UI mainly shows chat bubbles, the model should return a small structured payload behind the scenes.

Suggested shape:

```json
{
  "answer": "Wait until the top inch feels dry before watering.",
  "suggested_actions": [
    "Check the soil tonight",
    "Water tomorrow morning if the top inch is dry"
  ],
  "watch_signals": [
    "crispy tips",
    "drooping by evening"
  ]
}
```

Why keep this:

- enables future reminder creation
- enables future action chips
- gives us a bridge from chat into structured app state later

Do not auto-write these into plant memory in MVP.

After each assistant turn, optionally update:

- `rolling_summary`
- `open_questions_json`
- `last_advice_json`

This update should be compact and server-controlled. It is there to shrink future prompt size, not to create another user-visible artifact.

## Language Strategy

The chat system should support multilingual output without changing the core product shape.

Recommended approach:

- keep `name`, `chinese_name`, and `species` as separate fields
- add `preferred_language` to the user profile later
- ask the model to answer in `en` or `zh-Hans` depending on the user

The chat data model itself can remain language-agnostic.

## Codebase Mapping

### Backend

#### `/Users/alicia/Documents/Playground/my-garden/my_garden/data.py`

Add:

- table creation for `chat_threads`
- table creation for `chat_messages`
- `fetch_or_create_chat_thread(...)`
- `list_chat_messages(...)`
- `create_chat_message(...)`
- `update_chat_thread_memory(...)`
- serializers for thread and message payloads

#### `/Users/alicia/Documents/Playground/my-garden/my_garden/server.py`

Add:

- `GET /api/plants/:id/chat`
- `POST /api/plants/:id/chat/messages`

Ensure:

- user ownership checks follow current plant scoping rules
- chat only loads messages for the current user's plant

#### `/Users/alicia/Documents/Playground/my-garden/my_garden/plant_ai.py`

Add:

- `build_plant_chat_context(...)`
- `answer_plant_followup(...)`
- `summarize_plant_chat_memory(...)`

This should reuse the provider abstraction already in place instead of hard-coding OpenAI calls.

#### `/Users/alicia/Documents/Playground/my-garden/my_garden/ai_providers.py`

Add provider-facing method for plant follow-up chat, for example:

- `answer_plant_followup(...)`
- `summarize_plant_chat_memory(...)`

This keeps OpenAI and local VLM/text backends swappable.

### Frontend

#### `/Users/alicia/Documents/Playground/my-garden/static/index.html`

Add:

- new `chat-view` section

#### `/Users/alicia/Documents/Playground/my-garden/static/app.js`

Add:

- route handling for `#/plant/:id/chat`
- actions to load thread
- actions to send message
- state for active plant chat
- optional pinned diagnosis state

#### `/Users/alicia/Documents/Playground/my-garden/static/js/views/detail-view.js`

Add:

- `Ask follow-up` CTA near latest diagnosis
- `Ask about this diagnosis` CTA in expanded history rows

#### New file

Recommended new file:

- `/Users/alicia/Documents/Playground/my-garden/static/js/views/chat-view.js`

Responsibilities:

- render plant chat screen
- render pinned diagnosis card
- render message list
- render suggested prompt chips
- render composer

#### `/Users/alicia/Documents/Playground/my-garden/static/style.css`

Add styles for:

- plant chat screen
- message bubbles
- pinned diagnosis context card
- prompt chips
- loading state

## MVP Scope

### Included

- one persistent chat per plant
- follow-up entry from latest diagnosis
- follow-up entry from history diagnosis
- plant-scoped chat persistence
- grounded assistant replies using plant history
- suggested prompts
- rolling chat summary for token control
- no image replay on routine follow-up turns

### Not included

- global multi-plant chat
- multiple threads per plant
- image upload inside chat
- voice chat
- automatic reminder creation from chat
- auto-writing plant memory from chat
- chat search

## Recommended Build Order

### Phase 1: Backend foundation

1. Add `chat_threads` and `chat_messages`
2. Add serializers and CRUD helpers
3. Add `GET /api/plants/:id/chat`
4. Add `POST /api/plants/:id/chat/messages`

### Phase 2: AI answer path

1. Add `answer_plant_followup(...)`
2. Assemble plant context packet
3. Return natural answer plus structured actions
4. Save compact memory back onto the thread

### Phase 3: Frontend route and view

1. Add `chat-view`
2. Add route handling in `app.js`
3. Render message list and composer

### Phase 4: Entry points

1. Add `Ask follow-up` near latest read
2. Add `Ask about this diagnosis` in history rows
3. Support optional `checkin_id` anchor in route/state

### Phase 5: Polish

1. Suggested prompt chips
2. Empty state for first question
3. Loading and error states

## Success Criteria

We should consider the MVP successful if a user can:

1. Open a plant
2. Tap `Ask follow-up`
3. Ask a question without re-explaining the plant
4. Get a context-aware answer
5. Come back later and still see that plant's chat history

## Future Extensions

Once the MVP works, the best next upgrades are:

- `Summarize this plant's story`
- `Turn this answer into a reminder`
- `Pin this insight`
- `What changed since last week?`
- chat message search
- photo upload inside chat
- dynamic `Current pattern` summary generated from chat + check-ins

## Recommendation

Build this as a **plant-scoped follow-up layer**, not a generic chatbot.

Make token efficiency a first-class product rule:

- small recent context window
- rolling summary memory
- no default image replay
- no raw transcript replay

That keeps the product aligned with the real user need:

- a structured plant record
- plus an ongoing conversation that stays grounded in that plant's history

That combination is what makes My Garden better than a long raw ChatGPT thread.
