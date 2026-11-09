import { CheckCircleIcon } from "@heroicons/react/24/outline";
import { InteractivePlanetLine } from "@/shared/ui/animated-decorations/interactive-planet-line";

const checks = [
  "Нужно быстро находить сроки, суммы и требования в объёмных закупочных документах",
  "Важно проверить, что ответ подтверждается точной цитатой из источника",
  "Изменения извещения могут заменить прежние условия закупки",
  "Если документы расходятся или ответа нет, лучше узнать об этом заранее",
];
const cards = [
  [
    "Документы",
    "закупки в одном разборе",
    "Помощник помогает находить важные условия среди множества файлов и страниц.",
  ],
  [
    "Цитаты",
    "подтверждение каждого ответа",
    "Можно сразу сверить вывод с фрагментом исходного документа.",
  ],
  [
    "Контроль",
    "противоречий и пробелов",
    "Betelgeuse отмечает расхождения условий и сообщает, когда данных недостаточно.",
  ],
];

export function LandingAbout() {
  return (
    <section
      id="about"
      className="relative overflow-hidden scroll-mt-19 bg-dom-light py-18 max-[640px]:py-12"
    >
      <InteractivePlanetLine mirrored />
      <InteractivePlanetLine />
      <div className="mx-auto w-[calc(100%-64px)] max-w-[1480px] max-[640px]:w-[calc(100%-32px)] rounded-4xl border border-special-300 bg-content-0 px-11 py-16 max-[640px]:p-6">
        <div className="grid grid-cols-[1fr_1.027fr] gap-11 max-[1100px]:grid-cols-1 max-[640px]:gap-6 [&_ul]:list-none [&_li]:mb-3 [&_li]:flex [&_li]:items-center [&_li]:gap-3 [&_li]:border-b [&_li]:border-special-300 [&_li]:pb-3 [&_li]:text-body-base [&_li]:text-content-900 [&_svg]:shrink-0 [&_svg]:text-accent-500">
          <div>
            <p className="mb-1.5 text-body-sm font-medium text-accent-500">
              Для тех, кто работает с закупками
            </p>
            <h2>Когда в документах важна каждая цифра</h2>
            <p className="mt-1.5 text-body-lg text-content-600">
              Betelgeuse помогает участникам закупок разбирать условия,
              проверять ответы по источникам и замечать неоднозначности до
              подачи заявки.
            </p>
          </div>
          <ul>
            {checks.map((text) => (
              <li key={text}>
                <CheckCircleIcon width={24} height={24} />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-8 grid grid-cols-3 gap-4 max-[640px]:grid-cols-1 max-[640px]:gap-6 [&_article]:rounded-2xl [&_article]:bg-dom-light [&_article]:px-6 [&_article]:py-5 [&_h3]:text-h1 [&_h3]:font-medium [&_h4]:my-3 [&_h4]:text-h6 [&_h4]:font-medium [&_p]:text-body-sm">
          {cards.map(([title, subtitle, text]) => (
            <article key={title}>
              <h3>{title}</h3>
              <h4>{subtitle}</h4>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
