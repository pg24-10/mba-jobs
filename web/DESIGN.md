# mba-jobs design: Campus poster (direction C)

Picked by Pranav on 16 Nov 2026 from `design/two-directions.html`. Every screen of the site follows these rules. Change them only after asking.

## The idea

Each job function has its own colour and shape, like posters on a campus notice board. You spot your lane at a glance. Everything else stays calm: white cards on a light grey page, black text, round pills.

## Fonts

| Role | Font | Use |
|---|---|---|
| Headings, numbers, job titles | Jost 600–700 | Logo, lane counts, card titles, job page title, section headings |
| Everything else | Work Sans 400–600 | Body text, filters, facts, buttons |

No other fonts. No monospace.

## Colours

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#F1F2F4` | Page background |
| `--w` | `#FFFFFF` | Cards, panels, inputs |
| `--ink` | `#141414` | Text, selected states, main buttons |
| `--mut` | `#5E6268` | Secondary text (passes AA on white and on `--bg`) |
| `--line` | `#E4E5E8` | Hairlines, quiet pill backgrounds |
| `--r` | `#D7263D` | Poster red |
| `--y` | `#F5C400` | Poster yellow. Also the one "do something new" accent (resume button, Undo) |
| `--b` | `#1D4ED8` | Poster blue |

Rules:
- Red, yellow and blue appear only as function colours (tiles, card shapes, the job page header) and the yellow accent. They are never used for text on white.
- Text on yellow is always ink. Text on red, blue and black is white.
- The primary action is always a black pill. There is one per screen: "Read the full post and apply on <site>".

## Functions: colour and shape

| Function | Colour | Shape |
|---|---|---|
| Sales & BD | yellow | circle |
| Program management | blue | triangle |
| Operations | black | square |
| Consulting | red | square |
| Finance | yellow | triangle |
| Marketing | red | circle |
| Product | blue | circle |
| Analytics | blue | square |
| HR | red | half circle |
| Supply chain | black | triangle |
| General management | black | half circle |
| Growth | yellow | square |
| Strategy | red | triangle |
| Banking | blue | half circle |
| Investing | yellow | half circle |
| Technology | black | circle |
| Other | white | circle |

The shape on a tile or header uses the "partner" colour (yellow tile → red shape, blue → yellow, red → yellow, black → red), cropped off the top-right corner.

## Shapes and spacing

- Cards and panels: square corners, no shadow. A selected card gets a 3px ink inside border.
- Pills (buttons, filters, search): fully round.
- Spacing steps: 4, 6, 8, 12, 16, 24, 32 px.
- Card title 18px Jost; job page title 26px (23px on phones).
- The company name leads every card (Jost 600, 15px, ink) and the job page (Jost 700, 20px, linked to the company's site when we know it). It is never grey.
- Match tags: a small grey pill with "N match"; ink with white text at 70 and above.

## Layout

- **Laptop:** top bar (logo, Jobs / Saved / Applied with counts, search pill, How it works, Sign in). Under it, the function lane strip; then filter pills (the yellow "Match my resume" pill first) and sort; then a thin status line ("N roles match", active filters with ×, Clear all, Last updated). Then the list on the left and the job page on the right (about 500px), with the apply button fixed at the bottom of the job page.
- **Phone:** search pill, lane strip (scrolls sideways), filter chips (scroll sideways), status line, list, bottom bar with Jobs / Saved / Applied. Tapping a job opens the job page as its own screen with a round Back button and the apply button fixed at the bottom.

## Wording

- Plain and short. "Save", "Mark applied", "Hide", "Undo", "Clear all".
- Job page sections: "What you'd do", "What they're looking for", "Key skills".
- Under them: "Summary written by mba-jobs. The original post has the full details."
- The ISB badge says "Past ISB recruiter". Never show cluster, lineup or campus status.
- No big hero numbers.

## Never

- Gradients, glass blur, drop-shadow cards, emoji icons, purple.
- Copied job description text.
