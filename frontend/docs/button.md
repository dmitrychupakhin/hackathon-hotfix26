# Button

Реализация: `src/shared/ui/button.tsx`. Источник: Figma Buttons → Button blue
(`3:70`), прочитаны все 96 комбинаций. Название blue устарело: заливки зелёные.

Основа — установленный `@base-ui/react/button`, варианты — `cva`, слияние
классов — проектный `cn`. Дополнительные зависимости не добавлялись.

## API

- `variant`: `primary` (по умолчанию), `secondary`.
- `size`: `sm`, `md` (по умолчанию), `lg` — Small, Medium, Big в Figma.
- `icon`: React-элемент. Например, иконка из установленного `@heroicons/react`.
- `iconPosition`: `left` (по умолчанию), `right`, `only`.
- Для `only` обязательны `icon` и `aria-label`, текстовые children запрещены типами.
- `disabled`, `focusableWhenDisabled`, `render`, `nativeButton`, `ref`,
  обработчики событий и строка/функция `className` передаются через API Base UI.

```tsx
import { PlusCircleIcon } from "@heroicons/react/24/outline";
import { Button } from "@/shared/ui/button";

<Button>Сохранить</Button>
<Button variant="secondary" size="sm" disabled>Отмена</Button>
<Button size="lg" icon={<PlusCircleIcon />}>Добавить</Button>
<Button icon={<PlusCircleIcon />} iconPosition="right">Добавить</Button>
<Button icon={<PlusCircleIcon />} iconPosition="only" aria-label="Добавить" />
```

Иконки декоративные: название действия задаётся текстом кнопки или `aria-label`.
Для обработчиков событий пример должен находиться в Client Component.

## Геометрия

| Размер | Высота | Padding X | Текст / line-height | Иконка с текстом / отдельно |
| --- | --- | --- | --- | --- |
| sm | 40px | 16px | 14 / 20px | 18 / 20px |
| md | 48px | 24px | 16 / 24px | 20 / 24px |
| lg | 60px | 32px | 20 / 28px | 24 / 28px |

Расстояние до иконки — 12px, вес Golos Text — 400. Только иконка — квадрат.
Радиусы: sm Primary с текстом 10px; sm Secondary и sm только с иконкой 12px;
md 12px; lg 14px. Различие сохранено из макета.

## Состояния

| Вариант | Default | Hover | Pressed | Disabled |
| --- | --- | --- | --- | --- |
| Primary | Accent/400 | Accent/300 | Accent/300 + внутренняя обводка Accent/600 | Accent/200, текст Content/400 |
| Secondary | Прозрачный | Special/200 | Special/200 | Прозрачный, текст Special/300 |

У Secondary постоянная внутренняя обводка Special/300. Обычный текст обоих
вариантов — Special/100. Иконки наследуют цвет текста. Внутренняя обводка
сохраняет геометрию и соответствует INSIDE stroke в Figma.

Hover и Pressed — CSS-псевдоклассы взаимодействия, отдельного `state` prop нет.
Они отключены при `data-disabled`, включая `focusableWhenDisabled`.
После уточнения дизайна толщина внутренней рамки при нажатии обоих вариантов —
1.5px. Для keyboard focus также используется inset-ring 1.5px цвета Accent/600.
Outline для фокуса не используется. Рамка не выходит за границы кнопки.
Motion-анимаций в выбранном наборе нет.

По согласованному референсу Beady добавлен общий `transition-interaction`:
300ms / ease для цветов и обводки в обоих направлениях. Значения заданы
один раз в токенах `globals.css`, в компоненте нет собственных длительностей.
При уменьшении движения в настройках пользователя переход отключается.

## Проверка

TypeScript, Biome, компиляция Tailwind и серверный рендер проходят.
Геометрия и размеры иконок проверены по данным всех 96 комбинаций Figma.
Проверены disabled, focusableWhenDisabled, className callback и render ссылки.
Визуальная проверка и проверка событий в браузере пока не выполнены:
сервис управления браузером недоступен. Production-сборку блокирует запрет
среды на открытие порта обработчиком CSS Turbopack.
