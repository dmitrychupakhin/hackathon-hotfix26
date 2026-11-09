import { PaperAirplaneIcon } from "@heroicons/react/24/outline";
import Link from "next/link";
import { InteractiveEllipses } from "@/shared/ui/animated-decorations/interactive-ellipses";
import { InteractivePlanets } from "@/shared/ui/animated-decorations/interactive-planets";
import { buttonVariants } from "@/shared/ui/button-variants";

const stats = [
  ["Источник", "у каждого подтверждённого ответа есть цитата из документа"],
  ["Сверка", "система замечает разные значения в документах закупки"],
  ["Без догадок", "если подтверждения нет, помощник сообщает об этом"],
  ["Проверка", "цитаты и значения проходят автоматический контроль"],
];

export function LandingHero() {
  return (
    <section className="relative pt-21 pb-18 max-[640px]:pb-12">
      <InteractiveEllipses />
      <InteractivePlanets />
      <div className="relative mx-auto flex max-w-[1198px] flex-col items-center gap-6 text-center max-[1100px]:px-8 max-[640px]:px-4 [&_h1]:text-[80px] [&_h1]:leading-[1.15] [&_h1]:font-medium max-[1100px]:[&_h1]:text-[60px] max-[640px]:[&_h1]:text-[40px] [&_p]:text-body-lg [&_p]:text-content-500 max-[640px]:[&_p]:text-body-base">
        <h1>
          Betelgeuse — факты
          <br />
          вместо догадок
        </h1>
        <p>
          Сначала источник. Потом ответ.
          <br />
          Помощник Betelgeuse сверяет ответы с документами закупки, подтверждает
          их цитатами и честно отмечает пробелы и противоречия.
        </p>
        <Link href="/register" className={buttonVariants({ size: "lg" })}>
          Приступить
          <PaperAirplaneIcon aria-hidden="true" />
        </Link>
      </div>
      <div className="mx-auto mt-18 w-[calc(100%-64px)] max-w-[1480px] max-[640px]:w-[calc(100%-32px)] relative grid grid-cols-4 border-t border-special-300 pt-6 max-[640px]:grid-cols-1 max-[640px]:gap-6 [&>div]:px-6 [&>div+div]:border-l [&>div+div]:border-special-300 max-[640px]:[&>div+div]:border-l-0 [&_p]:text-body-base [&_p]:text-content-700">
        {stats.map(([title, text]) => (
          <div key={title}>
            <h2>{title}</h2>
            <p>{text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
