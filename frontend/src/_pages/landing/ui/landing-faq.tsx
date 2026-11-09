import { InteractiveEllipses } from "@/shared/ui/animated-decorations/interactive-ellipses";
import { InteractivePlanets } from "@/shared/ui/animated-decorations/interactive-planets";
import { CardQuestion } from "@/shared/ui/card-question";

export function LandingFaq() {
  return (
    <section id="faq" className="relative isolate scroll-mt-19 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 -scale-x-100">
        <InteractiveEllipses count={2} flipX />
        <InteractivePlanets count={5} flipX />
      </div>
      <div className="pointer-events-none absolute inset-0 -z-10 -scale-y-100">
        <InteractiveEllipses count={3} flipY />
        <InteractivePlanets count={5} flipY />
      </div>
      <div className="mx-auto w-[calc(100%-64px)] max-w-[1480px] max-[640px]:w-[calc(100%-32px)] grid min-h-[748px] grid-cols-[559fr_877fr] gap-11 py-18 max-[1100px]:grid-cols-1 max-[640px]:py-12">
        <div>
          <h2>Часто задаваемые вопросы</h2>
          <p className="mt-1.5 text-body-lg text-content-600">
            Как Betelgeuse помогает проверять закупочные документы и ответы по
            ним
          </p>
        </div>
        <div className="flex flex-col gap-4">
          <CardQuestion question="Что такое Betelgeuse?" open={false}>
            Это помощник для разбора закупочной документации. Он помогает
            находить условия, сроки и суммы, опираясь на текст документов.
          </CardQuestion>
          <CardQuestion question="Откуда берутся ответы?" open={false}>
            Ответы сверяются с материалами закупки и сопровождаются цитатой с
            указанием файла, чтобы их можно было проверить по первоисточнику.
          </CardQuestion>
          <CardQuestion
            question="Что будет, если документы противоречат друг другу?"
            open={false}
          >
            Betelgeuse отмечает расхождение и показывает оба значения с
            соответствующими цитатами, чтобы важное противоречие не осталось
            незамеченным.
          </CardQuestion>
          <CardQuestion
            question="А если нужной информации в документах нет?"
            open={false}
          >
            Помощник сообщит, что подтверждения не найдено, или укажет, что не
            уверен. Так ответ не подменяет отсутствующие данные догадкой.
          </CardQuestion>
          <CardQuestion question="Для кого создан проект?" open={false}>
            Для участников закупок, которым нужно быстрее разбирать большие
            пакеты документов и внимательно проверять условия перед подачей
            заявки.
          </CardQuestion>
        </div>
      </div>
    </section>
  );
}
