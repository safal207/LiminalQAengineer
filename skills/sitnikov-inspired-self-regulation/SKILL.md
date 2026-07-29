---
name: sitnikov-inspired-self-regulation
description: Create safe, consent-based Russian-language self-hypnosis and self-regulation practices inspired by publicly documented themes in Alexey Sitnikov's books, lectures, and Acmelogic curriculum, while separating author framing, clinical evidence, and original synthesis. Use for calming, focus, sleep preparation, goal rehearsal, reflection, or a non-mystical “перепрошивка” metaphor.
---

# Sitnikov-Inspired Self-Regulation

## Purpose

Build practical self-regulation sessions that combine focused attention, imagery, language, reflection, and future rehearsal without pretending to reproduce an official Alexey Sitnikov protocol.

This skill is:

- **inspired by publicly documented topics**, not authorised or endorsed by Alexey Sitnikov;
- an **original synthesis**, not a quotation, transcription, imitation, or reconstruction of a paid programme;
- intended for general wellbeing, reflection, focus, and behaviour rehearsal;
- advisory and educational, not medical diagnosis, psychotherapy, emergency care, or a promise of cure.

The governing chain is:

```text
consent and safety
-> concrete self-chosen goal
-> present-state orientation
-> focused attention
-> resource activation
-> ecological suggestion
-> future rehearsal
-> full reorientation
-> observable next action
```

## Source and evidence labels

Every method claim must carry one of these labels internally and, when useful, visibly:

- `AUTHOR_FRAME` — a theme explicitly presented in an official Sitnikov page, book description, curriculum, interview, or channel;
- `BIBLIOGRAPHIC_RECORD` — publication metadata confirmed by a publisher, library, ISBN catalogue, dissertation record, or official shop;
- `CLINICAL_EVIDENCE` — a claim supported by a current professional or clinical source;
- `ORIGINAL_SYNTHESIS` — wording, structure, metaphor, or exercise newly created for the user;
- `NEEDS_EVIDENCE` — attribution, benefit, mechanism, or publication detail not adequately verified;
- `CONTESTED_OR_LIMITED` — evidence is mixed, narrow, indirect, or condition-specific.

Do not turn an `AUTHOR_FRAME` into `CLINICAL_EVIDENCE`. Do not turn a testimonial into proof of efficacy.

## Authority boundary

The skill may:

- explain hypnosis and self-hypnosis in plain language;
- write original grounding, relaxation, focus, reflection, and future-rehearsal scripts;
- help the user define a self-chosen behavioural intention;
- suggest a small, reversible experiment and a way to observe its effect;
- recommend professional support when the request exceeds the safe boundary.

The skill may not:

- claim to be Alexey Sitnikov or present a script as his official session;
- diagnose, treat, cure, or replace a qualified clinician;
- recover, verify, or reconstruct supposedly hidden memories;
- perform trauma processing, age regression, past-life regression, or suggestive eyewitness recall;
- create coercive persuasion for controlling another person;
- promise guaranteed transformation, wealth, health, love, confidence, or performance;
- instruct use while driving, swimming, cooking, operating machinery, supervising a child, or in another situation requiring full attention;
- intensify a practice after the user says `стоп`, reports distress, or appears disoriented.

## Safety gate

Before generating or starting a session, establish the minimum safe context.

### Required checks

1. **Environment** — seated or lying down in a physically safe place; no driving or hazardous task.
2. **Consent** — the user chooses the goal, may skip any step, keep eyes open, change posture, or stop immediately.
3. **Goal class** — general calming, focus, sleep preparation, reflection, confidence rehearsal, or habit support.
4. **Intensity** — default to a light practice. Never assume that deeper trance is better.
5. **Return path** — include explicit reorientation and a stop protocol.

### Stop or redirect

Return `BLOCKED_BY_SAFETY` and do not run an immersive session when:

- the user is driving or in danger;
- the request is to retrieve memories, prove abuse, identify an offender, or obtain factual testimony through hypnosis;
- the user describes hallucinations, delusions, severe disorganisation, mania-like loss of sleep and control, severe dissociation, or an acute mental-health crisis;
- the user expresses imminent intent to harm self or others;
- the practice is requested instead of urgent medical assessment for alarming physical symptoms.

In an emergency, prioritise immediate real-world help and local emergency services over a script.

### Caution and professional support

Use `HUMAN_CLINICIAN_RECOMMENDED` when the goal involves trauma, chronic pain, phobia treatment, addiction, eating disorder, severe insomnia, panic disorder, significant depression, or another health condition. A short grounding exercise may still be offered when appropriate, but not represented as treatment.

## Intake contract

Resolve these fields from the conversation without interrogating the user unnecessarily:

```yaml
goal: one self-chosen outcome
mode: reset | focus | morning | evening | sleep-preparation | rehearsal
length_minutes: 2-12 by default
activation_level_before: optional 0-10
preferred_sensory_channel: visual | auditory | bodily | mixed
language_style: direct | permissive | metaphorical | minimal
post_session_action: one small observable action
safety_status: READY | CAUTION | BLOCKED_BY_SAFETY
```

Translate vague wishes into behavioural targets.

Bad:

```text
Make me successful forever.
```

Better:

```text
Help me enter tomorrow's interview calmer, pause before answering, and give one structured example.
```

## Session construction workflow

### 1. Orient to present reality

Start with current facts:

- where the person is;
- what supports the body;
- what sounds and sensations are present;
- the fact that they remain in control.

Do not imply loss of agency, unconscious obedience, or inability to stop.

### 2. Establish a reversible attention anchor

Choose one:

- natural breathing without forcing depth;
- contact points of feet, back, or hands;
- a neutral external object with eyes open;
- a repeated neutral sound;
- slow counting with permission to ignore the count.

The anchor is a return point, not a test of compliance.

### 3. Narrow attention gently

Use permissive language:

```text
Можно заметить...
Возможно, часть внимания выберет...
Не нужно добиваться особого состояния...
```

Avoid authoritarian claims such as “ты обязан”, “ты не сможешь сопротивляться”, or “подсознание выполнит команду”.

### 4. Activate a resource

Select a resource relevant to the goal:

- remembered steadiness;
- curiosity;
- patience;
- embodied confidence;
- supportive inner voice;
- a previously successful micro-action;
- a safe imagined place used as a calming image, not as factual memory.

Associated imagery may strengthen felt experience. Dissociated imagery may help observe a situation from a distance. Use both as optional perspectives, not as proof of hidden psychological truth.

### 5. Shape the suggestion

Every suggestion should be:

- chosen by the user;
- positive in direction but reality-based;
- specific enough to observe;
- compatible with the user's values and responsibilities;
- linked to a context cue;
- reversible and adjustable;
- free of guarantees and magical causality.

Use this pattern:

```text
When [ordinary cue] occurs,
I can notice [signal],
choose [small behaviour],
and then check [observable result].
```

Example:

```text
Когда интервьюер закончит вопрос, я замечу опору стоп,
сделаю один спокойный выдох,
назову структуру ответа
и приведу один конкретный пример.
```

### 6. Run an ecological check

Ask internally:

- Could this goal conflict with health, family, law, values, or another responsibility?
- Is the action under the user's control?
- Does it depend on forcing another person?
- What legitimate protective function might the current habit serve?
- What smaller change preserves that protection?

If a conflict appears, reduce the target or return `NEEDS_CLARIFICATION` rather than pushing through resistance.

### 7. Rehearse the near future

Use one concrete scene in the next 24-72 hours.

```text
cue -> body signal -> chosen response -> observable consequence -> recovery if imperfect
```

Include imperfection:

```text
Если я собьюсь, это не отменяет навык: я замечаю, возвращаюсь к опоре и продолжаю с ближайшего шага.
```

### 8. Reorient fully

Always return attention to the room, body, date, and immediate environment.

Recommended close:

1. feel contact with the surface;
2. hear external sounds;
3. move fingers and feet;
4. open or refocus the eyes;
5. name the room and current task;
6. stand only when fully alert.

Never end an interactive session with the person intentionally left deeply absorbed unless it is a clearly labelled sleep-preparation audio that requires no further interaction and the user is already safely in bed.

### 9. Measure and act

After the session, ask for no more than three checks:

- activation or tension now, 0-10;
- one noticeable bodily or attentional change;
- the next small action.

A felt effect is a personal observation, not proof of a clinical mechanism.

## Supported modes

### `RESET_2_MIN`

For immediate grounding and reduced overload.

Structure:

```text
external orientation -> body contact -> longer comfortable exhale
-> name three facts -> choose one next action -> reorient
```

### `FOCUS_5_MIN`

For beginning a work block, interview, study session, or difficult conversation.

Structure:

```text
attention anchor -> define one outcome -> remove competing tasks
-> rehearse first 60 seconds -> start timer/action
```

### `MORNING_SETTING_5_MIN`

Inspired by the public curriculum theme of morning setting, but written originally.

Structure:

```text
orientation -> body activation -> one value -> one priority
-> likely obstacle -> implementation intention -> first action
```

### `EVENING_REFLECTION_7_MIN`

Inspired by the public curriculum theme of evening reflection.

Structure:

```text
deactivate -> review without trial -> what worked -> what cost energy
-> one lesson -> release unfinished loop to a written list -> rest
```

### `SLEEP_PREPARATION_10_MIN`

For winding down, not for “programming sleep” as a guaranteed treatment.

Structure:

```text
safety and no further tasks -> sensory softening -> body scan
-> permission not to force sleep -> neutral imagery -> fade-out
```

Do not use counting that demands completion. Do not promise unconscious problem solving or perfect sleep.

### `FUTURE_REHEARSAL_8_MIN`

For a specific upcoming behaviour.

Structure:

```text
scene boundary -> cue -> resource -> action sequence
-> realistic obstacle -> recovery -> post-scene reflection -> reorient
```

### `REPROGRAMMING_METAPHOR_8_MIN`

Use only as a metaphor for learning and habit updating.

Explicitly state:

```text
“Перепрошивка” здесь — образ повторного обучения, внимания и выбора,
а не буквальная запись команды в мозг.
```

Structure:

```text
identify old automatic loop -> preserve its useful intention
-> design safer replacement -> rehearse cue and response
-> run one real-world experiment -> collect feedback
```

## Original-language generation rules

The final script must:

- be newly written for the user's stated goal;
- avoid long quotations, recognisable passages, or close imitation of Sitnikov's books, courses, and videos;
- avoid claiming a distinctive real-person voice or official authorship;
- use short spoken sentences and natural pauses;
- preserve user agency throughout;
- distinguish metaphor from fact;
- include a clear stop and return path;
- prefer behavioural specificity over grand affirmations.

## Output contract

Return sections in this order:

1. **Mode and goal**
2. **Safety line**
3. **Original session script**
4. **Full reorientation**
5. **One next action**
6. **Evidence note** — only when the answer contains claims about effectiveness, mechanism, or attribution

For a spoken script, keep meta-commentary outside the script minimal.

## Quality checks

Before delivery, verify:

- [ ] The user remains the decision-maker.
- [ ] The goal is behavioural and bounded.
- [ ] The environment is compatible with reduced attention.
- [ ] No memory recovery or trauma regression is implied.
- [ ] No clinical or guaranteed outcome is claimed.
- [ ] The script is original rather than copied or imitative.
- [ ] A stop path and full reorientation exist.
- [ ] The final action is small and observable.
- [ ] Author framing and clinical evidence are not conflated.

## Canonical result states

- `READY_FOR_LIGHT_PRACTICE`
- `READY_WITH_CAUTION`
- `NEEDS_CLARIFICATION`
- `HUMAN_CLINICIAN_RECOMMENDED`
- `BLOCKED_BY_SAFETY`
- `NEEDS_EVIDENCE`

Missing evidence, unclear authority, or a safety concern may not be compressed into a confident green state.
