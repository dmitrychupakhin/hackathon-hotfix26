import { LandingAbout } from "./landing-about";
import { LandingFaq } from "./landing-faq";
import { LandingFooter } from "./landing-footer";
import { LandingHeader } from "./landing-header";
import { LandingHero } from "./landing-hero";

export function LandingPage() {
  return (
    <div className="overflow-clip bg-content-0 text-special-100 [&_h2]:text-h2 [&_h2]:font-medium max-[640px]:[&_h2]:text-h4">
      <LandingHeader />
      <main>
        <LandingHero />
        <LandingAbout />
        <LandingFaq />
      </main>
      <LandingFooter />
    </div>
  );
}
