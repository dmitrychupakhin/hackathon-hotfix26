export function LandingFooter() {
  return (
    <footer
      id="footer"
      className="relative scroll-mt-19 mx-auto w-[calc(100%-64px)] max-w-[1480px] max-[640px]:w-[calc(100%-32px)] rounded-4xl border border-b-0 border-transparent p-11 max-[640px]:p-6"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -inset-px rounded-[inherit] border border-b-0 border-special-300 mask-[linear-gradient(to_bottom,#000,transparent)]"
      />
      <div className="grid grid-cols-[1fr_205px_205px] gap-[62px] max-[1100px]:grid-cols-2 max-[640px]:gap-6 [&>p]:max-w-[753px] [&>p]:text-h1 max-[1100px]:[&>p]:col-span-full max-[640px]:[&>p]:text-h3 [&_h3]:mb-3 [&_h3]:text-body-lg [&_h3]:text-content-700 [&_a]:block [&_a]:text-body-lg [&_a]:leading-8 [&_a]:text-content-900 [&_span]:block [&_span]:text-body-lg [&_span]:leading-8 [&_span]:text-content-900">
        <p>
          Воплощайте идеи в цифровую реальность вместе с командой Betelgeuse
        </p>
        <div>
          <h3>Меню</h3>
          <a href="#about">Наши работы</a>
          <a href="#about">О нас</a>
        </div>
        <div>
          <h3>Будем рады видеть вас</h3>
          {["ВКонтакте", "Телеграм", "GitHub", "Figma"].map((name) => (
            <span key={name}>{name} ↗</span>
          ))}
        </div>
      </div>
      <div className="mt-6 flex gap-[33px] border-t border-special-300 pt-6 text-body-base max-[640px]:flex-col max-[640px]:gap-3 [&>span+span]:text-accent-500">
        <span>© 2026 Команда Betelgeuse</span>
        <span>Политика конфиденциальности</span>
        <span>Пользовательское соглашение</span>
      </div>
    </footer>
  );
}
