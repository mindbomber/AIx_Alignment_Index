const steps = ['draft', 'in_review', 'approved', 'finalized']

export function WorkflowTimeline({ status }: { status: string }) {
  const current = steps.indexOf(status)
  return (
    <ol className="workflow" aria-label="Assessment review progress">
      {steps.map((step, index) => (
        <li
          className={index <= current ? 'complete' : ''}
          aria-current={step === status ? 'step' : undefined}
          key={step}
        >
          <span />
          {step.replace('_', ' ')}
        </li>
      ))}
    </ol>
  )
}
