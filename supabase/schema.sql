-- EdgeIQ Database Schema
-- Run in Supabase SQL editor: https://app.supabase.com → SQL Editor

-- ── Extensions ────────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ── Users ─────────────────────────────────────────────────────────────────────
create table if not exists users (
  id uuid primary key default uuid_generate_v4(),
  email text unique not null,
  telegram_chat_id text,
  bankroll numeric(12,2) default 0,
  timezone text default 'Africa/Lagos',
  created_at timestamptz default now()
);

-- ── Teams ─────────────────────────────────────────────────────────────────────
create table if not exists teams (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  short_name text,
  sport text not null check (sport in ('basketball', 'football')),
  league text not null,
  external_id text,
  created_at timestamptz default now(),
  unique(sport, external_id)
);

-- ── Matches ───────────────────────────────────────────────────────────────────
create table if not exists matches (
  id uuid primary key default uuid_generate_v4(),
  home_team_id uuid references teams(id),
  away_team_id uuid references teams(id),
  sport text not null check (sport in ('basketball', 'football')),
  league text not null,
  start_time timestamptz not null,
  status text default 'scheduled' check (status in ('scheduled', 'live', 'finished', 'cancelled')),
  home_score integer,
  away_score integer,
  result text check (result in ('home', 'draw', 'away')),
  draw_possible boolean default false,
  external_id text,
  created_at timestamptz default now(),
  unique(sport, external_id)
);

create index if not exists idx_matches_start_time on matches(start_time);
create index if not exists idx_matches_sport_league on matches(sport, league);
create index if not exists idx_matches_status on matches(status);

-- ── Basketball Stats ──────────────────────────────────────────────────────────
create table if not exists team_stats_basketball (
  id uuid primary key default uuid_generate_v4(),
  team_id uuid references teams(id),
  match_id uuid references matches(id) on delete cascade,
  is_home boolean not null,
  points integer,
  opp_points integer,
  rebounds integer,
  assists integer,
  fg_pct numeric(5,3),
  fg3_pct numeric(5,3),
  ft_pct numeric(5,3),
  turnovers integer,
  steals integer,
  blocks integer,
  recorded_at timestamptz default now()
);

create index if not exists idx_bb_stats_team on team_stats_basketball(team_id);
create index if not exists idx_bb_stats_match on team_stats_basketball(match_id);

-- ── Football Stats ────────────────────────────────────────────────────────────
create table if not exists team_stats_football (
  id uuid primary key default uuid_generate_v4(),
  team_id uuid references teams(id),
  match_id uuid references matches(id) on delete cascade,
  is_home boolean not null,
  goals integer,
  opp_goals integer,
  xg numeric(5,2),
  opp_xg numeric(5,2),
  shots integer,
  shots_on_target integer,
  possession numeric(5,2),
  corners integer,
  yellow_cards integer,
  red_cards integer,
  recorded_at timestamptz default now()
);

create index if not exists idx_fb_stats_team on team_stats_football(team_id);
create index if not exists idx_fb_stats_match on team_stats_football(match_id);

-- ── Predictions ───────────────────────────────────────────────────────────────
-- basketball: draw_prob is null (binary market)
-- football: home/draw/away all populated (3-way market)
create table if not exists predictions (
  id uuid primary key default uuid_generate_v4(),
  match_id uuid references matches(id) on delete cascade,
  sport text not null,
  model_version text not null,
  home_prob numeric(5,4) not null,
  draw_prob numeric(5,4),
  away_prob numeric(5,4) not null,
  confidence text check (confidence in ('high', 'medium', 'low')),
  value_flag boolean default false,
  brier_score numeric(6,4),
  claude_analysis jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_predictions_match on predictions(match_id);
create index if not exists idx_predictions_created on predictions(created_at);
create index if not exists idx_predictions_value on predictions(value_flag) where value_flag = true;

-- ── Odds ──────────────────────────────────────────────────────────────────────
create table if not exists odds (
  id uuid primary key default uuid_generate_v4(),
  match_id uuid references matches(id) on delete cascade,
  bookmaker text not null,
  market text not null default 'h2h',
  home_odds numeric(8,3),
  draw_odds numeric(8,3),
  away_odds numeric(8,3),
  recorded_at timestamptz default now(),
  unique(match_id, bookmaker, market)
);

create index if not exists idx_odds_match on odds(match_id);
create index if not exists idx_odds_bookmaker on odds(bookmaker);
create index if not exists idx_odds_recorded on odds(recorded_at);

-- ── Odds History (snapshots for line movement) ────────────────────────────────
create table if not exists odds_history (
  id uuid primary key default uuid_generate_v4(),
  match_id uuid references matches(id) on delete cascade,
  bookmaker text not null,
  market text not null,
  home_odds numeric(8,3),
  draw_odds numeric(8,3),
  away_odds numeric(8,3),
  snapshot_at timestamptz default now()
);

create index if not exists idx_odds_hist_match on odds_history(match_id);
create index if not exists idx_odds_hist_snapshot on odds_history(snapshot_at);

-- ── Arbitrage Alerts ──────────────────────────────────────────────────────────
create table if not exists arb_alerts (
  id uuid primary key default uuid_generate_v4(),
  match_id uuid references matches(id) on delete cascade,
  profit_pct numeric(6,4) not null,
  stakes_json jsonb not null,
  best_home_book text,
  best_draw_book text,
  best_away_book text,
  detected_at timestamptz default now(),
  notified boolean default false,
  expired boolean default false
);

create index if not exists idx_arb_detected on arb_alerts(detected_at);
create index if not exists idx_arb_notified on arb_alerts(notified) where notified = false;

-- ── Value Bets ────────────────────────────────────────────────────────────────
create table if not exists value_bets (
  id uuid primary key default uuid_generate_v4(),
  match_id uuid references matches(id) on delete cascade,
  selection text not null check (selection in ('home', 'draw', 'away')),
  edge_pct numeric(6,4) not null,
  model_prob numeric(5,4) not null,
  market_prob numeric(5,4) not null,
  best_odds numeric(8,3) not null,
  bookmaker text not null,
  ev numeric(8,4),
  detected_at timestamptz default now(),
  notified boolean default false,
  result text check (result in ('won', 'lost', 'void', 'pending')) default 'pending'
);

create index if not exists idx_vb_detected on value_bets(detected_at);
create index if not exists idx_vb_notified on value_bets(notified) where notified = false;

-- ── Bet Tracker ───────────────────────────────────────────────────────────────
create table if not exists bets (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  match_id uuid references matches(id),
  sport text,
  league text,
  selection text not null,
  bookmaker text not null,
  odds numeric(8,3) not null,
  stake numeric(10,2) not null,
  status text default 'pending' check (status in ('pending', 'won', 'lost', 'void', 'cashout')),
  pnl numeric(10,2),
  tag text check (tag in ('value', 'arb', 'tipster', 'system', 'gut')),
  notes text,
  confidence_stars smallint check (confidence_stars between 1 and 5),
  placed_at timestamptz default now(),
  settled_at timestamptz
);

create index if not exists idx_bets_user on bets(user_id);
create index if not exists idx_bets_match on bets(match_id);
create index if not exists idx_bets_status on bets(status);
create index if not exists idx_bets_placed on bets(placed_at);

-- ── Row Level Security ────────────────────────────────────────────────────────
alter table users enable row level security;
alter table bets enable row level security;
alter table predictions enable row level security;
alter table odds enable row level security;
alter table value_bets enable row level security;
alter table arb_alerts enable row level security;

-- Users can only see/edit their own data
create policy "users_own_data" on users
  for all using (auth.uid()::text = id::text);

create policy "bets_own_data" on bets
  for all using (auth.uid()::text = user_id::text);

-- Predictions, odds, arbs are readable by everyone (no personal data)
create policy "predictions_public_read" on predictions
  for select using (true);

create policy "odds_public_read" on odds
  for select using (true);

create policy "value_bets_public_read" on value_bets
  for select using (true);

create policy "arb_alerts_public_read" on arb_alerts
  for select using (true);
