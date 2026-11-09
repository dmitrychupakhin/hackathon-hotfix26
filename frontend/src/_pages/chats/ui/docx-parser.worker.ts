import { convertToHtml } from "mammoth/mammoth.browser";

self.onmessage = async ({ data }: MessageEvent<ArrayBuffer>) => {
  try {
    const result = await convertToHtml(
      { arrayBuffer: data },
      { externalFileAccess: false },
    );
    self.postMessage({ html: result.value });
  } catch {
    self.postMessage({
      error: "Не удалось отобразить DOCX. Используйте извлечённый текст ниже.",
    });
  }
};
