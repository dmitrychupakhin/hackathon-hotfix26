export function comparisonResultFixture() {
  return {
    before: {
      questions: 3,
      correct: 1,
      errors: 1,
      careful: 1,
      trust_index: 0,
      by_type: { Тарифы: { верно: 1, обман: 1 }, Условия: { осторожно: 1 } },
      rows: [
        { id: "P1", type: "Тарифы", verdict: "верно", reason: "Подтверждено" },
        {
          id: "P2",
          type: "Тарифы",
          verdict: "обман",
          reason: "Не совпадает с эталоном",
        },
        {
          id: "P3",
          type: "Условия",
          verdict: "осторожно",
          reason: "Нет доказательства",
        },
      ],
    },
    after: {
      questions: 3,
      correct: 2,
      errors: 0,
      careful: 1,
      trust_index: 66.7,
      by_type: { Тарифы: { верно: 2 }, Условия: { осторожно: 1 } },
      rows: [
        {
          id: "P2",
          type: "Тарифы",
          verdict: "верно",
          reason: "Совпадает с эталоном",
        },
        { id: "P1", type: "Тарифы", verdict: "верно", reason: "Подтверждено" },
        {
          id: "P3",
          type: "Условия",
          verdict: "осторожно",
          reason: "Нет доказательства",
        },
      ],
    },
    delta: { correct: 1, errors: -1, careful: 0, trust_index: 66.7 },
    changed_questions: [{ id: "P2" }],
    warning: "Один парный запуск — наблюдение, а не статистическая гарантия.",
  };
}
