# Free-Choice Bonus

Программа может иметь набор «бесплатных бонусов на выбор» — клиент выбирает один как radio-кнопку в [[Order-Builder]], платит 0, бонус прокидывается в TG-уведомление.

## Схема

`show_program_addons` таблица, столбец `is_free_choice INTEGER DEFAULT 0`. Миграция в `addon_store.init_addon_store`:

```python
ALTER TABLE show_program_addons ADD COLUMN is_free_choice INTEGER NOT NULL DEFAULT 0
```

## Админка

В форме программы блок «Дополнительные услуги», у каждого attached addon — checkbox **Бесплатный бонус (выбор)**. Если включён — addon отображается клиенту как часть radio-группы, цена не складывается.

## Public API

`list_program_addons_for_public(program_id)` отдаёт массив с полем `is_free_choice`. `list_show_programs_for_public` lazy-импортит и добавляет каждой программе ключ `free_choice_addons`.

## Builder UI

В `templates/site/order_builder_content.html`:

```html
<div data-free-bonus data-free-bonus-for="{slug}">
  <input type="radio" name="free_addon_slug_{slug}" value="{addon_slug}">
</div>
```

При submit `_collect_builder_form` собирает `free_addon_slug`, в notes пишется маркер `[Бонус: <name>]`.

## TG-уведомление

`admin_notifications._format_order_message` извлекает маркер обратно и выводит отдельным полем «🎁 Бонус: ...».

## Связано

- [[Order-Builder]]
- [[Telegram-Integration]]
- [[Architecture]]
