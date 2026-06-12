import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import path from 'node:path'

const credentials = {
  organization: process.env.AIX_E2E_ORG ?? 'aix-research',
  email: process.env.AIX_E2E_EMAIL ?? 'owner@example.com',
  password: process.env.AIX_E2E_PASSWORD ?? 'browser-test-password',
}

async function signIn(page: Parameters<typeof test>[0]['page']) {
  await page.goto('/')
  await page.getByLabel('Organization').fill(credentials.organization)
  await page.getByLabel('Email').fill(credentials.email)
  await page.getByLabel('Password').fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Indicator scoring' })).toBeVisible()
  await page
    .getByLabel('Choose assessment')
    .selectOption({ label: 'Customer Support Model · v1' })
}

test('author can edit and save an assessment', async ({ page }) => {
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Customer Support Model' })).toBeVisible()
  await expect(page.getByLabel('P1 score')).toHaveValue(/[0-5]/)

  await page.screenshot({
    path: path.resolve(
      process.cwd(),
      '../docs/design/aix-workspace-implementation.png',
    ),
  })

  await page.getByLabel('P1 score').selectOption('4')
  await page
    .getByLabel('Assessment notes')
    .fill('Validated against the current external factuality audit.')
  await page.getByRole('button', { name: 'Save draft' }).click()
  await expect(page.getByText('Draft saved')).toBeVisible()
  await expect(page.getByText('Documented').first()).toBeVisible()
})

test('workspace collapses cleanly at a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page)
  await expect(page.getByRole('button', { name: 'Assessments' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Systems' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Customer Support Model' })).toBeVisible()
  await page.screenshot({
    path: path.resolve(
      process.cwd(),
      '../docs/design/aix-workspace-mobile.png',
    ),
  })
})

test('authenticated product surfaces have no serious accessibility violations', async ({
  page,
}) => {
  await signIn(page)
  const assessmentResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(
    assessmentResults.violations.filter(({ impact }) =>
      ['serious', 'critical'].includes(impact ?? ''),
    ),
  ).toEqual([])

  await page.getByRole('button', { name: 'Systems', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Systems', exact: true })).toBeVisible()
  const systemsResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(
    systemsResults.violations.filter(({ impact }) =>
      ['serious', 'critical'].includes(impact ?? ''),
    ),
  ).toEqual([])
})

test('user can register a system, create an assessment, and upload evidence', async ({
  page,
}) => {
  const systemName = `E2E Evidence System ${Date.now()}`
  await signIn(page)
  await page.getByRole('button', { name: 'New', exact: true }).click()
  await page.getByRole('button', { name: 'System', exact: true }).click()
  await page.getByLabel('System name').fill(systemName)
  await page.getByLabel('Description').fill('Created through the product workflow.')
  await page.getByRole('button', { name: 'Create system' }).click()

  await expect(
    page.getByRole('heading', { name: systemName }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Add evidence' }).click()
  await page.getByLabel('Evidence file').setInputFiles({
    name: 'audit.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('traceable browser evidence'),
  })
  await page.getByRole('button', { name: 'Record evidence' }).click()
  await expect(page.getByText('audit', { exact: true })).toBeVisible()
  await expect(page.getByText('1 sources')).toBeVisible()
})
