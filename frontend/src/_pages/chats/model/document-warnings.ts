/** User-visible extraction limitations; raw diagnostic codes remain in the API. */
export function documentWarning(warning: string): string | undefined {
  if (warning === "docx_page_layout_unavailable") return;
  if (warning === "ocr_text_requires_verification")
    return "Текст распознан автоматически. Проверьте символы и числа по оригиналу.";
  if (warning === "encoding_assumed_cp1251")
    return "Текст прочитан в кодировке Windows-1251.";
  if (warning.startsWith("ocr_") || /^page_\d+_has_no_text_layer/.test(warning))
    return "Для чтения текста скана требуется распознавание OCR.";
  if (warning === "empty_document") return "В документе не найден текст.";
  if (/images|charts|objects|nonparagraph/.test(warning))
    return "Изображения и некоторые встроенные элементы не вошли в извлечённый текст.";
  if (warning === "spreadsheet_formula_uses_cached_value_without_recalculation")
    return "Значения формул взяты из сохранённой версии таблицы без пересчёта.";
  if (warning === "spreadsheet_values_are_raw_without_display_number_formats")
    return "Данные таблицы показаны без исходного форматирования чисел.";
  if (warning === "presentation_speaker_notes_not_extracted")
    return "Заметки докладчика не вошли в извлечённый текст.";
  return "При извлечении текста обнаружены ограничения. Проверьте исходный документ.";
}
