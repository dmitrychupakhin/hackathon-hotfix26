export function PromptGuidance() {
  return (
    <aside className="rounded-3xl border border-special-300 p-8">
      <h2 className="text-h5 font-medium">Как это работает</h2>
      <p className="mt-[7px] text-body-sm text-content-500">
        Общие инструкции для всех чатов.
      </p>
      <div className="mt-5 border-t border-special-300 pt-5">
        <div>
          <h3 className="text-[15px] leading-[22px] font-medium">
            01  Напишите инструкции
          </h3>
          <p className="mt-1.5 text-[13px] leading-[19px] text-content-500">
            Опишите желаемый стиль и правила ответов.
          </p>
        </div>
        <div className="mt-5">
          <h3 className="text-[15px] leading-[22px] font-medium">
            02  Сохраните инструкции
          </h3>
          <p className="mt-1.5 text-[13px] leading-[19px] text-content-500">
            Они будут добавляться к следующим сообщениям во всех чатах. Текущий
            ответ не изменится.
          </p>
        </div>
      </div>
    </aside>
  );
}
