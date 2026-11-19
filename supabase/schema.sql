-- STACY XMD schema. Run once in Supabase: SQL Editor > New query > paste > Run.

create table if not exists ig_users (
  id text primary key,
  username text,
  first_seen timestamptz default now(),
  last_seen timestamptz default now(),
  paused boolean default false,
  human_handoff boolean default false,
  blocked boolean default false
);

create table if not exists ig_messages (
  id bigserial primary key,
  user_id text not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now()
);
create index if not exists ig_messages_user_idx on ig_messages (user_id, created_at desc);

create table if not exists ig_comments (
  id bigserial primary key,
  comment_id text unique,
  media_id text,
  user_id text,
  username text,
  text text,
  reply text,
  action text,
  created_at timestamptz default now()
);

create table if not exists ig_rules (
  id bigserial primary key,
  trigger text not null,
  match_type text default 'contains' check (match_type in ('contains', 'exact')),
  reply text default '',
  dm_reply text,
  scope text default 'both' check (scope in ('dm', 'comment', 'both')),
  active boolean default true,
  created_at timestamptz default now()
);

create table if not exists processed_events (
  id text primary key,
  created_at timestamptz default now()
);

create table if not exists bot_settings (
  key text primary key,
  value text
);

-- The bot uses the service_role key, which bypasses RLS. Enabling RLS with no policies
-- keeps these tables private from the public anon key.
alter table ig_users enable row level security;
alter table ig_messages enable row level security;
alter table ig_comments enable row level security;
alter table ig_rules enable row level security;
alter table processed_events enable row level security;
alter table bot_settings enable row level security;

-- Example rules (edit or delete). Comment "LINK" -> public reply + private DM.
insert into ig_rules (trigger, match_type, reply, dm_reply, scope) values
  ('link', 'contains', 'Just sent you the link in your DMs! 📩', 'Here is the link you asked for: https://example.com', 'comment'),
  ('price', 'contains', 'You can find all our prices here: https://example.com/prices', null, 'dm');

-- Optional housekeeping: delete dedup rows older than 7 days (run manually or schedule with pg_cron).
-- delete from processed_events where created_at < now() - interval '7 days';
