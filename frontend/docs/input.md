# Input

Один публичный компонент: `src/shared/ui/input.tsx`.
Исходник получен через `npx shadcn@latest add input --yes` и адаптирован
под 32 варианта Figma Inputs / Variants base inputs (`3:628`).
Поведение и доступные подписи основаны на установленных Base UI Input и Field.

```tsx
import { MagnifyingGlassIcon } from "@heroicons/react/24/solid";
import { Input } from "@/shared/ui/input";

<Input label="Имя" placeholder="Введите имя" />
<Input label="Поиск" icon={<MagnifyingGlassIcon />} clearable />
<Input label="Почта" type="email" size="sm" error="Проверьте адрес" />
```

## API

- `icon` — произвольная декоративная иконка слева.
- `clearable` — разрешает Heroicons Solid `XMarkIcon` справа. По умолчанию false.
  Крестик появляется только при непустом значении. В disabled или readOnly поле
  он неактивен; при пустом значении скрыт.
- `label` — необязательная подпись. Без неё задайте `aria-label` или `aria-labelledby`.
- `error` — текст ошибки, красная внутренняя рамка и связанное сообщение
  с InformationCircleIcon. `invalid` отмечает ошибку без сообщения.
- `size`: `sm` (Small в Figma), `md` (Base, по умолчанию).
- `defaultValue` — начальное строковое значение с внутренним управлением.
- `value` + `onValueChange(value)` — управление из родительского Client Component.
  И ввод, и очистка уведомляют `onValueChange`. Для controlled-поля родитель
  должен принять новое значение; без обработчика оно остаётся неизменным.
- `onClear` — необязательное дополнительное уведомление об очистке.
- `clearLabel` — доступное название кнопки, по умолчанию «Очистить поле».
- `className` — внешняя композиция, `inputClassName` — сам контрол
  (строка или функция состояния Base UI), `ref` — DOM-контрол.

Поддерживаются `name`, `type`, `required`, `disabled`, `readOnly`, `autoComplete`
и остальные нативные свойства Base UI Input. `onChange` относится к настоящим
событиям ввода; для уведомлений об изменении и очистке используйте `onValueChange`.
Сброс формы восстанавливает `defaultValue` во внутреннем режиме; в controlled-режиме
сбросом управляет родитель. После очистки фокус возвращается в поле.
Встроенный крестик браузера у `type="search"` скрыт: крестик определяется только
флагом `clearable`.

## Дизайн

| Свойство | sm | md |
| --- | --- | --- |
| Высота | 44px | 48px |
| Текст / line-height | 14 / 20px | 16 / 24px |
| Иконки | 20px | 24px |

Общие параметры: Golos Text 400, радиус 12px, padding 12px / 16px,
gap до иконок 12px, gap между подписью, контролом и ошибкой 2px.
Ошибка — 12/16px, вес 500, иконка 14px с gap 4px.

| Состояние | Фон | Внутренняя рамка 1px |
| --- | --- | --- |
| Обычное | DOM/Light | Special/300 |
| Фокус | Content/0 | Special/302 |
| Ошибка, включая фокус | DOM/Light | Error/600 |

Текст и подпись — Content/900; placeholder и боковые иконки — Special/302.
Переходы задаёт общий `transition-interaction` с reduced-motion.
Ширина гибкая, без фиксированного минимума 250px из Figma.

Названия `Icon=Right` в Figma неточны: фактически эти варианты содержат
две иконки, как `Both`. В коде сочетания выражаются `icon` и `clearable`.

Прежние InputField, InputGroup и SearchInput удалены; потребителю не нужно
собирать обычное поле из нескольких публичных компонентов.
