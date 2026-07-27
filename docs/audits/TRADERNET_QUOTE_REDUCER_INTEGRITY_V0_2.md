# Tradernet quote reducer integrity audit v0.2

## Зачем нужен второй слой

PR #120 подтвердил узкий, но повторяемый сигнал публичного demo quote stream: при растущих `n` и `rev` значение `ltt` многократно возвращается примерно на 15 минут назад.

Сам по себе server payload ещё не доказывает пользовательский дефект. Этот аудит проверяет следующий причинный переход:

```text
публичный q event
→ обычный monotonic n/rev reducer
→ shallow merge partial payload
→ видимое состояние котировки
```

Параллельно та же trace проигрывается через guarded reducer, который не позволяет более старому market time без явного provenance перезаписывать `ltt`, `ltp` и `lts`.

## Проверяемые claims

### TRD-RED-001 · Видимый откат времени

Может ли reducer, который принимает только неубывающие `n/rev`, всё равно показать пользователю более старое время последней сделки?

### TRD-RED-002 · Откат цены вместе со временем

Содержат ли backward-time payloads изменённый `ltp` или `lts`, то есть способны ли они перезаписать не только подпись времени, но и price/size state?

### TRD-RED-003 · Повторная инициализация после resubscribe

Повторная идентичная подписка уже вызывала новые `init=1` snapshots. Аудит проверяет, заменяют ли они более новое клиентское состояние более старым.

### TRD-RED-004 · Отсутствие provenance

Есть ли в противоречивых payloads явное поле, которое различает real-time и delayed time domains, источник, entitlement или режим? Отсутствие такого поля является system-contract сигналом, но не доказывает конкретный upstream producer.

## Модель решения

```text
trace не содержит material rollback
→ NOT_OBSERVED

rollback есть, но не проходит пороги повторяемости
→ SIGNAL

обычный reducer детерминированно откатывает visible state
в двух тикерах и двух connection phases,
а guarded reducer предотвращает тот же эффект
→ CONFIRMED_DEFECT_CANDIDATE

backward-time payload меняет ltp/lts
→ PRICE_STATE_DEFECT_CANDIDATE

повторный init snapshot есть, но не старее текущего state
→ REINITIALIZATION_SIGNAL

повторный init snapshot старее текущего state
→ DEFECT_CANDIDATE
```

## Границы

Аудит остаётся публичным и неавторизованным:

- два тикера;
- один WebSocket одновременно;
- один controlled disconnect/reconnect;
- одна повторная идентичная подписка;
- без market depth;
- без портфеля, аккаунта, ордеров и финансовых операций;
- без malformed messages, fuzzing, concurrency и load testing;
- без утверждений об order execution impact или upstream venue.

## Почему это глубже предыдущей проверки

Первый слой отвечает: **«сервер прислал противоречивые timestamps?»**

Этот слой отвечает: **«достаточно ли этих сообщений, чтобы стандартная клиентская архитектура показала пользователю stale state, и какой минимальный contract предотвращает эффект?»**

## Артефакты

```text
tradernet-public-quotes-reconnect.json
tradernet-public-quote-temporal-integrity.json
tradernet-quote-subscription-idempotency.json
tradernet-quote-reducer-integrity.json
tradernet-quote-reducer-integrity.md
manifest.json
artifact-receipt.json
```

## Ограничение вывода

Даже подтверждённый reducer-level finding не доказывает, что production Tradernet UI использует именно такой reducer. Он доказывает, что обычная и широко применяемая monotonic-sequence shallow-merge модель детерминированно уязвима к наблюдаемой public demo trace. Проверка точной production implementation требует authorised exact-build evidence.
