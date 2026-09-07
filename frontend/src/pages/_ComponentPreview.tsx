/**
 * TEMPORARY — Task 1 scaffolding only. Not a real route.
 *
 * A flat catalogue of the shared design system so the components can be
 * reviewed visually before any page exists. Task 2 adds the real /login and
 * /register pages; this preview stays on `/` until Task 3 wires the full
 * route table, then this file is deleted.
 *
 * See specs/frontend-phase/tasks.md — Task 1.
 */
import type { ReactNode } from 'react'
import { AppShell } from '@/components/shell/AppShell'
import { Button } from '@/components/ui/Button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card'
import { PriorityPill, type Priority } from '@/components/ui/PriorityPill'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { StatusPill, type Status } from '@/components/ui/StatusPill'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { Timeline, type TimelineStep } from '@/components/ui/Timeline'
import { TextInput } from '@/components/ui/TextInput'
import { Textarea } from '@/components/ui/Textarea'

const ALL_STATUSES: Status[] = [
  'open',
  'in_progress',
  'resolved',
  'closed',
  'draft',
]

const ALL_PRIORITIES: Priority[] = ['low', 'medium', 'high']

const SAMPLE_ROWS: { title: string; status: Status; updated: string }[] = [
  { title: 'Laptop will not boot after update', status: 'open', updated: '2h ago' },
  { title: 'VPN access for new contractor', status: 'in_progress', updated: '1d ago' },
  { title: 'Monitor replacement request', status: 'resolved', updated: '3d ago' },
  { title: 'Offboarding — revoke all access', status: 'closed', updated: '2w ago' },
]

const TIMELINE_STEPS: TimelineStep[] = [
  { label: 'Submitted', meta: 'Mon 09:14', filled: true },
  { label: 'Triaged', meta: 'Mon 11:02', filled: true },
  { label: 'In progress', meta: 'Tue 08:30', filled: true },
  { label: 'Resolved', meta: 'Pending', filled: false },
]

function Section({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-3 border-b border-border pb-8">
      <h2 className="text-h3 font-semibold text-text-primary">{title}</h2>
      {children}
    </section>
  )
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-3">{children}</div>
}

export default function ComponentPreview() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-h1 font-bold text-text-primary">
          Design system preview
        </h1>
        <p className="text-dense text-text-secondary">
          Temporary Task 1 scaffolding — removed once real pages exist.
        </p>
      </header>

      <Section title="Button">
        <Row>
          <Button>Primary action</Button>
          <Button variant="secondary">Secondary action</Button>
          <Button disabled>Disabled</Button>
        </Row>
      </Section>

      <Section title="Form primitives">
        <div className="flex max-w-sm flex-col gap-4">
          <TextInput placeholder="Empty text input" />
          <TextInput defaultValue="Filled text input" />
          <TextInput defaultValue="Disabled text input" disabled />
          <Textarea placeholder="Empty textarea" />
          <Textarea defaultValue="Disabled textarea" disabled />
          <Select>
            <SelectTrigger>
              <SelectValue placeholder="Select a priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="low">Low</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="high">High</SelectItem>
            </SelectContent>
          </Select>
          <Select disabled defaultValue="general">
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="general">General</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Section>

      <Section title="Card">
        <Card className="max-w-sm">
          <CardHeader>
            <CardTitle>Flat card</CardTitle>
            <CardDescription>
              Hairline border, no shadow, 4px radius.
            </CardDescription>
          </CardHeader>
          <CardContent>
            Body copy sits at the base 14px size with 1.5 line-height.
          </CardContent>
          <CardFooter>
            <Button>Confirm</Button>
            <Button variant="secondary">Cancel</Button>
          </CardFooter>
        </Card>
      </Section>

      <Section title="Table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Request</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {SAMPLE_ROWS.map((row) => (
              <TableRow key={row.title}>
                <TableCell>{row.title}</TableCell>
                <TableCell>
                  <StatusPill status={row.status} />
                </TableCell>
                <TableCell className="text-text-secondary">
                  {row.updated}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section title="StatusPill — all five states">
        <Row>
          {ALL_STATUSES.map((status) => (
            <StatusPill key={status} status={status} />
          ))}
        </Row>
      </Section>

      <Section title="PriorityPill — all three states">
        <Row>
          {ALL_PRIORITIES.map((priority) => (
            <PriorityPill key={priority} priority={priority} />
          ))}
        </Row>
      </Section>

      <Section title="Timeline — filled and hollow steps">
        <Timeline steps={TIMELINE_STEPS} />
      </Section>

      <Section title="AppShell — full-viewport sidebar shell">
        <div className="overflow-hidden rounded-card border border-border">
          <AppShell>
            <h2 className="text-h3 font-semibold text-text-primary">
              Content area
            </h2>
            <p className="text-body text-text-secondary">
              Pages render here. The sidebar has exactly two destinations.
            </p>
          </AppShell>
        </div>
      </Section>
    </div>
  )
}
