# «Монетка» outside-in audit v0.1

## Цель

Независимо проверить публичные неавторизованные поверхности торговой сети «Монетка» через три линзы:

- QA и целостность контента;
- системный анализ каналов, состояний и правил;
- бизнес-анализ доверия, установки приложения и покупки.

Репозиторий является центром контракта и доказательств. Аудит не разрешает контакт с компанией, вход, ввод адреса, изменение корзины, оформление или оплату заказа, активацию промокода, исправление продукта, deployment или merge.

## Публичный контур

```text
https://monetka.ru/
https://monetka.ru/action/
https://monetka.ru/info/user-agreement/
https://www.monetka.ru/urfo
Google Play: ru.mntk.dostavka.prod
App Store: id6742408188
```

Raw probe выполняет по одному последовательному GET на allowlisted URL. Browser slice открывает каждый URL в desktop и mobile Chromium, не нажимает элементы управления и сохраняет текст, hashes, screenshots, console/network summary, структуру и keyboard Tab trace.

## Source-to-rendered adjudication

Первая exact-матрица показала границу доступного независимому наблюдателю:

- страницы `monetka.ru`, включая соглашение и перенаправленный `/urfo`, ответили HTTP `401`; settled browser page имела служебный title `HTTP 403` и не содержала целевого пользовательского текста;
- Google Play и App Store воспроизвели публичное описание приложения в desktop и mobile;
- Google Play не показал первоначально выбранный marker `18+`; внизу страницы отображалась собственная платформенная классификация `M (17+)`;
- официальный ответ разработчика на Google Play направляет пользователя «Монетки» в MAX- и Telegram-боты с именем `LENTAcompany`.

HTTP/WAF-ограничение не считается дефектом продукта и не обходится. Claims, зависящие от сайта и соглашения, остаются `NEEDS_EVIDENCE`.

## Итоговые findings

### MON-001 · Устаревшая акция legacy-сайта — NEEDS_EVIDENCE

Поисковый контур ранее показывал акцию 1–7 июня 2026 года, но exact raw/browser наблюдение перенаправилось на `monetka.ru/urfo` и получило служебный ответ. Текущий видимый дефект не заявляется.

### MON-002 · Возрастная рассинхронизация — NEEDS_EVIDENCE

App Store отображает 13+, а Google Play — платформенную классификацию `M (17+)`; соглашение не удалось воспроизвести из audit environment. Платформы используют разные модели рейтинга, поэтому это контекстный сигнал, а не подтверждённый дефект или юридический вывод.

### MON-003 · Канальная модель web/app-заказа — NEEDS_EVIDENCE

Сайт и соглашение недоступны exact browser observer из-за служебного ответа. Наличие web checkout и применимые правила без контекста компании не утверждаются.

### MON-004 · Условия первого заказа без размера скидки — CONFIRMED_PRODUCT_DEFECT_CANDIDATE

Google Play и App Store в desktop и mobile показывают:

```text
Действует на первый заказ от 1200 ₽ на товары без скидок.
Максимальная скидка — 1 000 ₽.
```

При этом в settled listing text не указаны процент или размер исходного предложения. Пользователь не может вычислить обещанную выгоду до установки.

### MON-005 · «Доставка от 30 минут» — CONFIRMED_PRODUCT_DEFECT_CANDIDATE

Обе карточки приложения в desktop и mobile используют «с доставкой от 30 минут» и «привезём ... от 30 минут». Такая конструкция обозначает 30 минут или дольше и делает ключевое обещание скорости неоднозначным. Финальная severity требует редакционной оценки владельца продукта.

### MON-006 · Privacy disclosure Google Play — PUBLIC_DISCLOSURE_SIGNAL_ONLY

Google Play в desktop и mobile публикует developer declaration о возможной передаче личной и финансовой информации, о том, что данные не шифруются, и о возможности запросить удаление.

Жёсткий потолок finding:

```text
PUBLIC_DISCLOSURE_SIGNAL_ONLY
```

Без тестирования реализации нельзя делать выводы о transport/storage encryption, архитектуре, фактической обработке, exploitability или уязвимости.

### MON-007 · Качество текста соглашения — NEEDS_EVIDENCE

Выбранные source/search markers не воспроизведены в exact browser UI из-за служебного ответа сайта. Редакционный дефект не заявляется как подтверждённый.

### MON-008 · Cross-brand support routing — CONFIRMED_PRODUCT_DEFECT_CANDIDATE

В официальном ответе разработчика на отзыв о проблеме заказа «Монетки» пользователь направляется по адресам:

```text
max.ru/lentacompany_bot
t.me/LENTAcompany_bot
```

Оба маршрута видимы в desktop и mobile Google Play. Требуется контекст владельца: shared support route может быть намеренным, поэтому аудит не утверждает неправильного получателя или раскрытия данных. Подтверждён сам cross-brand trust/routing signal.

## Лестница доказательств

```text
поисковый или cached фрагмент
→ NEEDS_EVIDENCE

маркер воспроизведён в текущем публичном HTTP-ответе
→ PRODUCT_SIGNAL

тот же issue воспроизведён в settled desktop + mobile UI
→ CONFIRMED_PRODUCT_DEFECT_CANDIDATE

публичная security/privacy декларация без проверки реализации
→ PUBLIC_DISCLOSURE_SIGNAL_ONLY

контекст владельца продукта и человеческая оценка
→ финальная severity / решение о сотрудничестве
```

## Границы полномочий

Запрещены:

- авторизация и регистрация;
- ввод адреса или персональных данных;
- нажатия CTA и отправка форм;
- изменение корзины;
- создание, отмена или оплата заказа;
- промокоды и бонусные механики;
- прямое API, security, fuzzing, enumeration и load testing;
- обход служебных ограничений сайта;
- внешняя публикация или контакт;
- remediation, deployment, delivery и merge.

## Артефакты

Raw:

```text
reports/monetka/public-audit-v0.1/result.json
reports/monetka/public-audit-v0.1/summary.md
reports/monetka/public-audit-v0.1/exact-attempt.json
reports/monetka/public-audit-v0.1/ARTIFACT_SHA256SUMS.txt
```

Rendered:

```text
reports/monetka/rendered-audit-v0.2/monetka-rendered-result.json
reports/monetka/rendered-audit-v0.2/monetka-rendered-summary.md
reports/monetka/rendered-audit-v0.2/*.png
reports/monetka/rendered-audit-v0.2/exact-attempt.json
reports/monetka/rendered-audit-v0.2/ARTIFACT_SHA256SUMS.txt
```

## Ограничения суждения

- Публичный контент не раскрывает владельцев CMS, support templates, release process и внутренних источников данных.
- Возрастные рейтинги магазинов приложений используют разные платформенные методики.
- Служебный ответ сайта ограничивает coverage, но сам по себе не является finding.
- Developer declarations не заменяют техническую проверку реализации.
- Видимый LENTA-branded маршрут не доказывает, кто фактически владеет ботом и как обрабатываются сообщения.
- Бизнес-влияние остаётся `PLAUSIBLE_NOT_MEASURED`.
