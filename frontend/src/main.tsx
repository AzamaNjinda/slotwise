import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  request,
  dayIn,
  clock,
  type Booking,
  type Session,
  type Space,
  type Workspace,
} from "./api";
import "./styles.css";

function Icon({ name = "space" }: { name?: string }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {name === "calendar" ? (
        <>
          <rect x="3" y="5" width="18" height="16" rx="3" />
          <path d="M7 3v4m10-4v4M3 11h18m-13 5h2m4 0h2" />
        </>
      ) : name === "people" ? (
        <>
          <circle cx="9" cy="8" r="3" />
          <path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m5 10v-3a6 6 0 0 0-3-5" />
        </>
      ) : name === "arrow" ? (
        <path d="M5 12h14m-6-6 6 6-6 6" />
      ) : (
        <>
          <rect x="3" y="3" width="7" height="7" rx="2" />
          <rect x="14" y="3" width="7" height="7" rx="2" />
          <rect x="3" y="14" width="7" height="7" rx="2" />
          <rect x="14" y="14" width="7" height="7" rx="2" />
        </>
      )}
    </svg>
  );
}
function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    ref.current?.querySelector<HTMLInputElement>("[autofocus]")?.focus();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button
          className="icon-button"
          onClick={close}
          aria-label="Close dialog"
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
function App() {
  const [session, setSession] = useState<Session | null>(null),
    [workspaceId, setWorkspaceId] = useState(""),
    [day, setDay] = useState(""),
    [spaces, setSpaces] = useState<Space[]>([]),
    [bookings, setBookings] = useState<Booking[]>([]),
    [view, setView] = useState("Spaces"),
    [kind, setKind] = useState("all"),
    [search, setSearch] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [bookingSpace, setBookingSpace] = useState<Space | null>(null),
    [editing, setEditing] = useState<Space | "new" | null>(null);
  const retry = useRef({ payload: "", key: "" });
  const workspace = session?.workspaces.find((w) => w.id === workspaceId);
  async function loadSession() {
    try {
      const s = await request<Session>("/session/");
      setSession(s);
      if (s.workspaces.length) {
        setWorkspaceId(s.workspaces[0].id);
        setDay(dayIn(s.workspaces[0].timezone));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void loadSession();
  }, []);
  const refreshSequence = useRef(0);
  async function refresh(w: Workspace, date: string) {
    const sequence = ++refreshSequence.current;
    setLoading(true);
    setError("");
    try {
      const query = `?workspace=${w.id}`;
      const [r, b] = await Promise.all([
        request<Space[]>("/resources/" + query),
        request<Booking[]>("/bookings/" + query + "&date=" + date),
      ]);
      if (sequence !== refreshSequence.current) return;
      setSpaces(r);
      setBookings(b);
    } catch (e) {
      if (sequence === refreshSequence.current) {
        setError((e as Error).message);
        setSpaces([]);
        setBookings([]);
      }
    } finally {
      if (sequence === refreshSequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (workspace && day) void refresh(workspace, day);
  }, [workspaceId, day]);
  async function signIn(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      await request("/login/", "POST", Object.fromEntries(f));
      await loadSession();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    try {
      await request("/logout/", "POST", {});
      setSession({ user: null, workspaces: [] });
      setSpaces([]);
      setBookings([]);
      setNotice("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function reserve(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!workspace || !bookingSpace) return;
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const payload = {
      ...Object.fromEntries(f),
      resource: bookingSpace.id,
      attendees: Number(f.get("attendees")),
    };
    const serialized = JSON.stringify(payload);
    if (retry.current.payload !== serialized)
      retry.current = { payload: serialized, key: crypto.randomUUID() };
    try {
      await request(
        "/bookings/?workspace=" + workspace.id,
        "POST",
        payload,
        retry.current.key,
      );
      setDay(String(f.get("date")));
      setBookingSpace(null);
      setNotice("Your space is booked. You’re all set.");
      await refresh(workspace, String(f.get("date")));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel(b: Booking) {
    if (!workspace) return;
    setBusy(true);
    setError("");
    try {
      await request(
        `/bookings/${b.id}/cancel/?workspace=${workspace.id}`,
        "POST",
        {},
      );
      setNotice("Booking cancelled. The space is available again.");
      await refresh(workspace, day);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveSpace(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!workspace || !editing) return;
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const data = {
      name: f.get("name"),
      kind: f.get("kind"),
      floor: f.get("floor"),
      capacity: Number(f.get("capacity")),
      description: f.get("description"),
      amenities: f.getAll("amenities"),
      active: f.get("active") === "on",
    };
    try {
      await request(
        `/resources/${editing === "new" ? "" : editing.id + "/"}?workspace=${workspace.id}`,
        editing === "new" ? "POST" : "PATCH",
        data,
      );
      setEditing(null);
      setNotice("Space details saved.");
      await refresh(workspace, day);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!session?.user)
    return (
      <main className="login">
        <section className="login-story">
          <a className="brand" href="/">
            ✳ <span>slotwise</span>
          </a>
          <div>
            <span className="eyebrow">ROOM TO DO YOUR BEST WORK</span>
            <h1>
              Good work starts
              <br />
              with the right space.
            </h1>
            <p>
              Find a quiet corner. Bring your team together.
              <br />
              Make room for what’s next.
            </p>
            <div className="abstract" aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
          </div>
          <small>A workspace booking portfolio by Azama Njinda</small>
        </section>
        <section className="login-form">
          <span className="eyebrow">YOUR WORKSPACE, SIMPLIFIED</span>
          <h2>Welcome back.</h2>
          <p>Sign in to find your next space.</p>
          <form onSubmit={signIn}>
            <label>
              Email or username
              <input
                name="username"
                type="text"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy || loading}>
              {busy ? "Signing in…" : "Sign in to your workspace"}{" "}
              <Icon name="arrow" />
            </button>
          </form>
          {import.meta.env.DEV && (
            <div className="demo-note">
              <strong>Local demo</strong>
              <p>
                Manager: manager@example.invalid
                <br />
                Member: member@example.invalid
              </p>
              <p>Password: Slotwise-demo-only!</p>
              <small>
                Run the seed command in the README first. Fictional accounts,
                local use only.
              </small>
            </div>
          )}
        </section>
      </main>
    );
  if (!workspace)
    return (
      <main className="empty">
        <h1>No workspace yet</h1>
        <p>Ask an administrator to add your account to a workspace.</p>
        <button onClick={signOut}>Sign out</button>
      </main>
    );
  const confirmed = bookings.filter((b) => b.status === "confirmed");
  const filtered = spaces.filter(
    (s) =>
      (view === "Manage spaces" || s.active) &&
      (kind === "all" || s.kind === kind) &&
      `${s.name} ${s.floor} ${s.description}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const visibleBookings = (
    view === "My bookings"
      ? bookings.filter((b) => b.owner_id === session.user!.id)
      : bookings
  ).toSorted((a, b) => a.starts_at.localeCompare(b.starts_at));
  const hours = confirmed.reduce(
    (n, b) => n + (Date.parse(b.ends_at) - Date.parse(b.starts_at)) / 3600000,
    0,
  );
  const minutes = (value: string) => {
    const [h, m] = value.split(":").map(Number);
    return h * 60 + m;
  };
  const opening = minutes(workspace.opens_at),
    duration = minutes(workspace.closes_at) - opening;
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/">
          ✳ <span>slotwise</span>
        </a>
        <div className="workspace-label">
          <span className="workspace-symbol">N</span>
          <div>
            <strong>{workspace.name}</strong>
            <small>Shared spaces. Better days.</small>
          </div>
        </div>
        {session.workspaces.length > 1 && (
          <label>
            Workspace
            <select
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
            >
              {session.workspaces.map((w) => (
                <option value={w.id} key={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {[
            "Spaces",
            "My bookings",
            "Team schedule",
            ...(workspace.role === "manager" ? ["Manage spaces"] : []),
          ].map((v, i) => (
            <button
              key={v}
              className={view === v ? "selected" : ""}
              onClick={() => setView(v)}
            >
              <Icon
                name={i === 0 ? "space" : i === 2 ? "people" : "calendar"}
              />
              {v}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="tip">
            <span>MAKE ROOM FOR FOCUS</span>
            <p>
              A little planning.
              <br />A better working day.
            </p>
            <Icon name="calendar" />
          </div>
          <div className="profile">
            <span className="avatar">
              {session.user.name
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")}
            </span>
            <div>
              <strong>{session.user.name}</strong>
              <small>
                {workspace.role === "manager"
                  ? "Workspace manager"
                  : "Workspace member"}
              </small>
            </div>
          </div>
          <button className="sign-out" onClick={signOut}>
            Sign out ↗
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span>
            Workspace <span className="breadcrumb">/ {view}</span>
          </span>
          <span className="zone">◷ {workspace.timezone}</span>
          <button className="mobile-signout" onClick={signOut}>
            Sign out
          </button>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">A LITTLE SPACE GOES A LONG WAY</span>
              <h1>
                {view === "Spaces"
                  ? "Find your flow."
                  : view === "My bookings"
                    ? "Your day, planned."
                    : view === "Manage spaces"
                      ? "Spaces that work."
                      : "Room for everyone."}
              </h1>
              <p>
                {view === "Spaces"
                  ? "Discover a space for every kind of work."
                  : view === "Manage spaces"
                    ? "Keep your workspace organised and ready for the team."
                    : "See what’s happening across your workspace."}
              </p>
            </div>
            <label className="date-label">
              Viewing date
              <input
                aria-label="Viewing date"
                type="date"
                value={day}
                onInput={(e) => {
                  if (e.currentTarget.value) setDay(e.currentTarget.value);
                }}
              />
            </label>
          </div>
          <div className="stats">
            <div>
              <span className="stat-icon">
                <Icon />
              </span>
              <div>
                <strong>{spaces.filter((s) => s.active).length}</strong>
                <span>Spaces to make your own</span>
              </div>
            </div>
            <div>
              <span className="stat-icon peach">
                <Icon name="calendar" />
              </span>
              <div>
                <strong>{confirmed.length}</strong>
                <span>Bookings on this day</span>
              </div>
            </div>
            <div>
              <span className="stat-icon lilac">◷</span>
              <div>
                <strong>
                  {Number(hours.toFixed(1))}
                  <small> hrs</small>
                </strong>
                <span>Reserved across the team</span>
              </div>
            </div>
          </div>
          {notice && (
            <div className="notice" role="status">
              ✓ {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                ×
              </button>
            </div>
          )}
          {error && !bookingSpace && !editing && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {loading && (
            <p className="loading" role="status">
              Refreshing your workspace…
            </p>
          )}
          {view === "Spaces" || view === "Manage spaces" ? (
            <>
              <div className="section-heading">
                <div>
                  <h2>
                    {view === "Manage spaces"
                      ? "Manage your spaces"
                      : "A space for your next idea"}
                  </h2>
                  <p>
                    Opening hours {workspace.opens_at.slice(0, 5)}–
                    {workspace.closes_at.slice(0, 5)} · All times in{" "}
                    {workspace.timezone}
                  </p>
                </div>
                {view === "Manage spaces" && (
                  <button
                    className="primary"
                    onClick={() => {
                      setError("");
                      setEditing("new");
                    }}
                  >
                    ＋ Add a space
                  </button>
                )}
              </div>
              <div className="filters">
                <div className="tabs">
                  {[
                    ["all", "All spaces"],
                    ["room", "Meeting rooms"],
                    ["desk", "Desks"],
                    ["studio", "Studios"],
                  ].map(([k, label]) => (
                    <button
                      key={k}
                      className={kind === k ? "active" : ""}
                      onClick={() => setKind(k)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <input
                  type="search"
                  placeholder="Search for a space…"
                  aria-label="Search spaces"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="cards">
                {filtered.map((s, i) => {
                  const slots = confirmed.filter((b) => b.resource === s.id);
                  return (
                    <article className="space-card" key={s.id}>
                      <div className={"space-art art-" + (i % 4)}>
                        <span className="kind-tag">
                          {s.kind === "room"
                            ? "MEETING ROOM"
                            : s.kind.toUpperCase()}
                        </span>
                        <div className={"furniture furniture-" + s.kind}>
                          <i />
                          <i />
                          <i />
                          <i />
                        </div>
                        <span className="capacity">
                          <Icon name="people" /> {s.capacity}
                        </span>
                      </div>
                      <div className="card-body">
                        <div className="card-title">
                          <h3>{s.name}</h3>
                          <span
                            className={"dot " + (!s.active ? "archived" : "")}
                          >
                            {s.active ? "Active" : "Archived"}
                          </span>
                        </div>
                        <span className="floor">{s.floor}</span>
                        <p className="description">{s.description}</p>
                        <div className="amenities">
                          {s.amenities.map((a) => (
                            <span key={a}>{a}</span>
                          ))}
                        </div>
                        <div className="timeline-label">
                          <span>Day at a glance</span>
                          <span>
                            {slots.length} booking
                            {slots.length === 1 ? "" : "s"}
                          </span>
                        </div>
                        <div
                          className="timeline"
                          aria-label={`${slots.length} confirmed bookings`}
                        >
                          {slots.map((b) => (
                            <span
                              key={b.id}
                              title={`${b.title}: ${clock(b.starts_at, workspace.timezone)}–${clock(b.ends_at, workspace.timezone)}`}
                              style={{
                                left: `${Math.max(0, ((minutes(clock(b.starts_at, workspace.timezone)) - opening) / duration) * 100)}%`,
                                width: `${Math.min(100, ((Date.parse(b.ends_at) - Date.parse(b.starts_at)) / 60000 / duration) * 100)}%`,
                              }}
                            />
                          ))}
                        </div>
                        <div className="time-label">
                          <span>{workspace.opens_at.slice(0, 5)}</span>
                          <span>{workspace.closes_at.slice(0, 5)}</span>
                        </div>
                        <div className="card-actions">
                          <button
                            className="book-button"
                            disabled={!s.active}
                            onClick={() => {
                              setError("");
                              setBookingSpace(s);
                            }}
                          >
                            Book this space <Icon name="arrow" />
                          </button>
                          {view === "Manage spaces" && (
                            <button
                              className="edit-button"
                              onClick={() => {
                                setError("");
                                setEditing(s);
                              }}
                            >
                              Edit
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
              {!filtered.length && !loading && (
                <div className="empty">
                  No spaces match your search. Try another filter.
                </div>
              )}
            </>
          ) : (
            <section className="schedule">
              <div className="section-heading">
                <div>
                  <h2>
                    {view === "My bookings"
                      ? "Your reservations"
                      : "The team’s day"}
                  </h2>
                  <p>Cancel a booking to free the space for someone else.</p>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Booking / space</th>
                      <th>Booked by</th>
                      <th>Time</th>
                      <th>Status</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleBookings.map((b) => (
                      <tr key={b.id}>
                        <td>
                          <strong>{b.title}</strong>
                          <small>
                            {b.resource_name} · {b.attendees} people
                          </small>
                        </td>
                        <td>{b.owner_name}</td>
                        <td>
                          {clock(b.starts_at, workspace.timezone)} –{" "}
                          {clock(b.ends_at, workspace.timezone)}
                        </td>
                        <td>
                          <span className={"badge " + b.status}>
                            {b.status === "cancelled"
                              ? "Cancelled"
                              : Date.parse(b.ends_at) < Date.now()
                                ? "Completed"
                                : "Confirmed"}
                          </span>
                        </td>
                        <td>
                          {b.can_cancel &&
                            Date.parse(b.ends_at) > Date.now() && (
                              <button
                                className="cancel"
                                disabled={busy}
                                onClick={() => void cancel(b)}
                              >
                                Cancel
                              </button>
                            )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!visibleBookings.length && (
                <div className="empty">
                  <Icon name="calendar" />
                  <h3>A little breathing room.</h3>
                  <p>No bookings for this day. Find a space to get started.</p>
                  <button className="primary" onClick={() => setView("Spaces")}>
                    Explore spaces
                  </button>
                </div>
              )}
            </section>
          )}
          <footer>
            Made for more thoughtful working days.
            <span>Slotwise · Portfolio edition</span>
          </footer>
        </div>
      </main>
      {bookingSpace && (
        <Modal
          title={"Book " + bookingSpace.name}
          close={() => {
            if (!busy) {
              setBookingSpace(null);
              setError("");
            }
          }}
        >
          <p className="modal-intro">
            {bookingSpace.capacity} people · {workspace.timezone} ·{" "}
            {workspace.opens_at.slice(0, 5)}–{workspace.closes_at.slice(0, 5)}
          </p>
          <form onSubmit={reserve}>
            <label>
              What are you planning?
              <input
                name="title"
                required
                maxLength={100}
                placeholder="e.g. Product planning"
                autoFocus
              />
            </label>
            <label>
              Date
              <input
                name="date"
                type="date"
                defaultValue={day}
                min={dayIn(workspace.timezone)}
                required
              />
            </label>
            <div className="form-row">
              <label>
                Start time
                <input
                  name="start_time"
                  type="time"
                  defaultValue="09:00"
                  min={workspace.opens_at.slice(0, 5)}
                  max={workspace.closes_at.slice(0, 5)}
                  required
                />
              </label>
              <label>
                End time
                <input
                  name="end_time"
                  type="time"
                  defaultValue="10:00"
                  min={workspace.opens_at.slice(0, 5)}
                  max={workspace.closes_at.slice(0, 5)}
                  required
                />
              </label>
            </div>
            <label>
              Number of people
              <input
                name="attendees"
                type="number"
                min="1"
                max={bookingSpace.capacity}
                defaultValue="1"
                required
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <p className="hint">
              Availability is checked when you confirm. If a space is taken,
              choose another time.
            </p>
            <button className="primary" disabled={busy}>
              {busy ? "Checking availability…" : "Confirm booking"}{" "}
              <Icon name="arrow" />
            </button>
          </form>
        </Modal>
      )}
      {editing && (
        <Modal
          title={editing === "new" ? "Add a space" : "Edit " + editing.name}
          close={() => {
            if (!busy) {
              setEditing(null);
              setError("");
            }
          }}
        >
          <form onSubmit={saveSpace}>
            <label>
              Space name
              <input
                name="name"
                maxLength={100}
                defaultValue={editing === "new" ? "" : editing.name}
                required
                autoFocus
              />
            </label>
            <div className="form-row">
              <label>
                Kind
                <select
                  name="kind"
                  defaultValue={editing === "new" ? "room" : editing.kind}
                >
                  <option value="room">Meeting room</option>
                  <option value="desk">Desk</option>
                  <option value="studio">Studio</option>
                </select>
              </label>
              <label>
                Capacity
                <input
                  name="capacity"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue={editing === "new" ? 4 : editing.capacity}
                  required
                />
              </label>
            </div>
            <label>
              Floor
              <input
                name="floor"
                maxLength={50}
                defaultValue={
                  editing === "new" ? "Ground floor" : editing.floor
                }
              />
            </label>
            <label>
              Description
              <textarea
                name="description"
                maxLength={300}
                rows={3}
                defaultValue={editing === "new" ? "" : editing.description}
              />
            </label>
            <fieldset>
              <legend>Amenities</legend>
              <div className="checks">
                {[
                  "Wi-Fi",
                  "Display",
                  "Whiteboard",
                  "Video calls",
                  "Natural light",
                  "Quiet zone",
                ].map((a) => (
                  <label key={a}>
                    <input
                      type="checkbox"
                      name="amenities"
                      value={a}
                      defaultChecked={
                        editing !== "new" && editing.amenities.includes(a)
                      }
                    />
                    {a}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="checkbox">
              <input
                name="active"
                type="checkbox"
                defaultChecked={editing === "new" || editing.active}
              />
              Available for new bookings
            </label>
            <p className="hint">
              Archiving preserves existing reservations and booking history.
            </p>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Saving…" : "Save space"}
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
