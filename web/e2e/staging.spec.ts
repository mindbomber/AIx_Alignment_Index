import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const credentials = {
  organization: process.env.AIX_E2E_ORG ?? '',
  email: process.env.AIX_E2E_EMAIL ?? '',
  password: process.env.AIX_E2E_PASSWORD ?? '',
}

test.skip(
  process.env.AIX_STAGING_ACCEPTANCE !== 'true',
  'Runs only against the deployed staging environment.',
)

test('staging supports authentication, navigation, and accessible UI', async ({
  page,
}) => {
  expect(credentials.organization).not.toBe('')
  expect(credentials.email).not.toBe('')
  expect(credentials.password).not.toBe('')

  await page.goto('/')
  await page.getByLabel('Organization').fill(credentials.organization)
  await page.getByLabel('Email').fill(credentials.email)
  await page.getByLabel('Password').fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Systems' })).toBeVisible()

  await page.getByRole('button', { name: 'Systems', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Systems', exact: true })).toBeVisible()

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(
    results.violations.filter(({ impact }) =>
      ['serious', 'critical'].includes(impact ?? ''),
    ),
  ).toEqual([])
})
