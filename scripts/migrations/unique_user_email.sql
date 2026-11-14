-- Check for existing duplicates before applying this migration. Do not delete accounts automatically.
-- SELECT lower(btrim(email)), count(*) FROM public.users WHERE email IS NOT NULL AND btrim(email) <> ''
-- GROUP BY lower(btrim(email)) HAVING count(*) > 1;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_normalized_unique
    ON public.users (lower(btrim(email)))
    WHERE email IS NOT NULL AND btrim(email) <> '';
