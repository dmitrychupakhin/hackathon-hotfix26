# Типографика

Источник: 44 локальных Text styles из Figma, группы Headline, Body и Label.
Отдельная страница в Figma не нужна: параметры прочитаны из определений стилей.

## Использование

```tsx
<h1 className="text-h1 font-semibold">Заголовок</h1>
<p className="text-body-base font-normal">Основной текст</p>
<span className="text-label-md font-medium text-content-500">Подпись</span>
```

React-компонент Typography не добавляется. Размер, line-height и letter-spacing
задаются одним Tailwind-классом, вес — отдельным `font-*`, цвет — `text-*`.
Название h1–h6 описывает внешний вид и не выбирает HTML-тег: семантический уровень
заголовка определяется структурой страницы.

## Размеры

| Figma | Класс | Размер | Line-height |
| --- | --- | --- | --- |
| Headline/h1 | `text-h1` | 48px | 56px |
| Headline/h2 | `text-h2` | 36px | 44px |
| Headline/h3 | `text-h3` | 32px | 40px |
| Headline/h4 | `text-h4` | 28px | 36px |
| Headline/h5 | `text-h5` | 24px | 32px |
| Headline/h6 | `text-h6` | 20px | 28px |
| Body/large | `text-body-lg` | 18px | 28px |
| Body/base | `text-body-base` | 16px | 24px |
| Body/small | `text-body-sm` | 14px | 20px |
| Label/medium | `text-label-md` | 12px | 16px |
| Label/small | `text-label-sm` | 10px | 12px |

Все стили используют локальный Golos Text и letter-spacing 0.
В CSS размеры заданы в rem (в таблице эквивалент при корневом размере 16px),
line-height — пропорцией из Figma. Цвет и отступы в текстовые стили не входят.
Типографика по умолчанию для body — Body/base/regular (16/24px, вес 400).

## Веса

| Вариант Figma | Класс | Вес |
| --- | --- | --- |
| regular | `font-normal` | 400 |
| medium | `font-medium` | 500 |
| semibold | `font-semibold` | 600 |
| bold | `font-bold` | 700 |

Исключение в исходнике: `Headline/h1/bold` фактически имеет SemiBold / wght 600.
Для точного воспроизведения этого стиля используйте `text-h1 font-semibold`.
Он совпадает с `Headline/h1/semibold`. Значение не исправлено на 700 без решения
дизайнера; `font-bold` в проекте сохраняет обычное значение 700.

## Конфигурация

- `src/app/globals.css` — 11 токенов `--text-*` с line-height и tracking, четыре веса.
- Стандартная шкала размеров Tailwind сброшена: используйте проектные имена,
  а не `text-sm`, `text-xl` и т. п.
- `src/shared/utils/cn.ts` регистрирует новые имена как размеры шрифта.
  Без этой настройки пакет cn считает неизвестный `text-h1` цветом и удаляет
  его при слиянии с `text-content-900`.
- Кнопка и поле используют общие текстовые токены. Большая кнопка использует
  геометрию `text-h6` (20/28px); это не превращает её в заголовок.
- Добавление нового размера требует токенов в CSS и имени в конфигурации cn.

Семейство подключено через next/font/local в layout.tsx; веса 400–700 доступны
в существующем variable-файле (полный диапазон файла 400–900).
