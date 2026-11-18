import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How it works · mba jobs",
  description: "Where mba jobs finds roles, how it scores them, and what it keeps about you.",
};

const Mark = () => (
  <span className="mark" aria-hidden="true">
    <svg width="16" height="16" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#D7263D" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><rect width="100" height="100" fill="#1D4ED8" /></svg>
    <svg width="16" height="16" viewBox="0 0 100 100"><polygon points="50,0 100,100 0,100" fill="#F5C400" /></svg>
  </span>
);

export default function About() {
  return (
    <div className="ab">
      <header className="top">
        <Link className="logo" href="/"><Mark />mba jobs</Link>
        <nav className="nav" aria-label="Pages">
          <Link href="/">Jobs</Link>
        </nav>
      </header>

      <main className="ab-main">
        <section className="ab-hero y">
          <svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="50" fill="#D7263D" /></svg>
          <h1>Jobs in India that suit an MBA, in one place.</h1>
          <p>
            Every day this site reads the big job boards and hundreds of company career pages, keeps the roles an MBA
            would want, and sorts them by job function so you can find your lane quickly.
          </p>
        </section>

        <section className="ab-sec">
          <h2>How it works</h2>
          <ol className="ab-steps">
            <li><b>Collect.</b> Each morning a script searches for new roles posted in India and pulls them in.</li>
            <li><b>Read.</b> Each post is read and tagged: the function, level, experience asked for, pay, city, industry and whether it asks for an MBA.</li>
            <li><b>Score.</b> Every role gets a fit score from 1 to 5 for how well it suits an MBA. The list shows 3 and up unless you change it.</li>
            <li><b>Clear out.</b> A role is taken down once it is 30 days old, or once it has not been seen on any site for 30 days.</li>
          </ol>
        </section>

        <section className="ab-sec two">
          <div>
            <h2>Where roles come from</h2>
            <ul>
              <li>LinkedIn</li>
              <li>Naukri</li>
              <li>Indeed</li>
              <li>IIMjobs</li>
              <li>Company career sites (Greenhouse, Lever, Workday and others)</li>
            </ul>
            <p>The apply button always takes you to the original post, the company&apos;s own site first when there is one.</p>
          </div>
          <div>
            <h2>What the fit score means</h2>
            <ul className="ab-fit">
              <li><b>5</b> Made for an MBA: asks for one, or is a classic post-MBA role.</li>
              <li><b>4</b> A strong match for MBA skills and level.</li>
              <li><b>3</b> A good option; an MBA helps.</li>
              <li><b>1–2</b> Possible, but an MBA isn&apos;t what they&apos;re after.</li>
            </ul>
            <p>&quot;Past ISB recruiter&quot; marks companies that have hired from ISB before.</p>
          </div>
        </section>

        <section className="ab-sec two">
          <div>
            <h2>Resume matching</h2>
            <p>
              Add your resume and every role gets a match score out of 100, from the roles you want, your years of
              work, your background, industries, cities and skills.
            </p>
            <p>
              Your resume is read in your browser and never uploaded. Only the short profile it produces is kept: on
              this device, and in your account if you sign in. You can edit or delete it any time.
            </p>
          </div>
          <div>
            <h2>Signing in</h2>
            <p>
              You can use the site without an account. Signing in with Google keeps your saved and applied roles and
              your profile across devices. We only see your name and email address. Delete your account from the menu
              under your initial, and everything goes with it.
            </p>
          </div>
        </section>

        <section className="ab-sec">
          <h2>Good to know</h2>
          <ul>
            <li>The summaries are written by mba-jobs. The original post has the full details and is what counts.</li>
            <li>Tags are read by software and can be wrong. If a role looks off, check the original post.</li>
            <li>A role can close on the company&apos;s side before it leaves this list. If a post says it no longer takes applications, hide it.</li>
          </ul>
        </section>

        <footer className="ab-by">
          <p>Built by Pranav Gupta.</p>
          <Link className="go" href="/">Browse roles</Link>
        </footer>
      </main>
    </div>
  );
}
