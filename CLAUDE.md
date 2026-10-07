# For the AI assistant in this repo

You're in the Morning Loop package. The person you're helping is most likely setting it up for the first time, or asking how it works.

## If they want to set it up, or say "start", "onboard", "set me up"

Run `/onboard` (or follow `commands/onboard.md` if your client hasn't installed the commands yet: `python3 scripts/install.py` does that). Show the onboarding map first, so they see what each stage costs and what it gives them before they spend any time. One stage at a time, each proven with a test read and confirmed by them before it's marked done.

## If they ask what it is or whether it's worth it

Answer from `README.md` and the stage table. Be concrete about what each stage adds to the brief (the `brief_sample` in each `stages/*.md` file is a real example). Be honest about the limits: the brief is made on their computer, so it arrives when the computer is on; drafts get good only once they add a few examples of their own work; some tool and client combinations aren't supported yet (`connectors/README.md`).

## Rules that always hold

- **Their files are theirs.** Everything the loop writes lives in `morning/` inside the folder they chose. Never touch anything else in that folder. Never put their files in this package folder.
- **Read-only first.** Connect tools with read-only access whenever the connector allows it.
- **No secrets in files.** Never write a token, password or webhook URL into `morning/config.yml` or any file. Connectors keep their own credentials; webhooks go in environment variables.
- **Nothing leaves their machine without their yes.** No task created, no email or message sent, no page published, no calendar changed, unless they approve that specific item in the moment.
- **Never fabricate.** A number or status comes from a source you read, or it says "not checked".
- **Don't oversell.** If a stage won't help them (no meetings, no tracker), say so and suggest skipping it.

## If you change the package itself

Run `python3 scripts/check_clean.py` and `python3 tests/run.py` before committing. The first keeps the package free of any person's or company's context; the second runs the engine self-tests and a full install-and-onboard rehearsal in a throwaway folder.
