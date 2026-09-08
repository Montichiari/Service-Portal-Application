import { Link, useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import { StatusPill } from '@/components/ui/StatusPill'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { mockRequests } from '@/data/mockRequests'

/**
 * Requests Dashboard (`/`) — the post-login landing page, so it uses AppShell.
 * Read-only list view: no forms, no validation, no network calls (design.md
 * per-page data strategy, requirements.md section 4, tasks.md Task 5).
 *
 * Rows come from the hardcoded mockRequests array and show title, status
 * (StatusPill) and a pre-formatted "last updated" string. Clicking a row — or
 * its title link — navigates to `/requests/:id` for that row. "New request"
 * goes to `/requests/new`.
 *
 * Layout: bounded to the table/dashboard width and centered in the content
 * area per design-tokens.md "Content width" (the shared .content-dashboard
 * class). Below --bp-mobile the "Last updated" column is dropped via
 * `hidden md:table-cell` on its header and cells — the same Table component
 * with fewer columns rendered, not a separate stacked-card layout (Task 5,
 * confirmed decision).
 */
export default function RequestsDashboardPage() {
  const navigate = useNavigate()

  return (
    <AppShell>
      <div className="content-dashboard flex flex-col gap-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex flex-col gap-1">
            <h1 className="text-h2 font-semibold text-text-primary">Requests</h1>
            <p className="text-dense text-text-secondary">
              Track the status of your submitted service requests.
            </p>
          </div>
          <Button asChild className="self-start">
            <Link to="/requests/new">New request</Link>
          </Button>
        </header>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden md:table-cell">Last updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockRequests.map((request) => (
              <TableRow
                key={request.id}
                onClick={() => navigate(`/requests/${request.id}`)}
                className="cursor-pointer hover:bg-card"
              >
                <TableCell>
                  {/*
                   * A real link so the row is keyboard-reachable and
                   * open-in-new-tab works; the row-level onClick above is
                   * mouse-only sugar. stopPropagation keeps a link click from
                   * also firing the row handler (same destination, avoids a
                   * double navigate). Styled as plain text — not accent blue —
                   * so it can't be confused with a status pill (design-tokens.md
                   * principle 1).
                   */}
                  <Link
                    to={`/requests/${request.id}`}
                    onClick={(event) => event.stopPropagation()}
                    className="font-semibold text-text-primary hover:underline"
                  >
                    {request.title}
                  </Link>
                </TableCell>
                <TableCell>
                  <StatusPill status={request.status} />
                </TableCell>
                <TableCell className="hidden text-text-secondary md:table-cell">
                  {request.lastUpdated}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </AppShell>
  )
}
