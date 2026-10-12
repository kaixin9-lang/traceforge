import {test,expect} from '@playwright/test';
test('real command review, edit, rejection and container execution',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'项目与工具',exact:true}).click();
 await page.locator('.project-selector button').filter({hasText:'Python 故障演示'}).click();
 const command=page.getByLabel('隔离命令');await command.fill('python -c "print(\'rejected-review-test\')"');
 await page.getByRole('button',{name:'生成审核',exact:true}).click();await expect(page.locator('.approval')).toBeVisible();
 await page.locator('.approval').getByRole('button',{name:'拒绝',exact:true}).click();await expect(page.locator('.approval')).toHaveCount(0);
 const token='traceforge-browser-approved-'+Date.now();await command.fill('python -c "print(\''+token+'\')"');await page.getByRole('button',{name:'生成审核',exact:true}).click();
 await expect(page.locator('.approval')).toBeVisible();await page.locator('.approval').getByRole('button',{name:'修改方案',exact:true}).click();
 const editor=page.getByLabel('修改修复提案');const proposal=JSON.parse(await editor.inputValue());proposal.description='浏览器编辑后的隔离命令测试';await editor.fill(JSON.stringify(proposal,null,2));
 await page.locator('.approval').getByRole('button',{name:'保存并重新审核',exact:true}).click();await expect(page.locator('.approval')).toContainText('浏览器编辑后的隔离命令测试');
 await page.locator('.approval').getByRole('button',{name:'批准执行',exact:true}).click();await expect(page.locator('.approval')).toHaveCount(0,{timeout:30000});
 const record=page.locator('.action-history details').filter({hasText:token}).first();await expect(record).toBeVisible({timeout:30000});await record.locator('summary').first().click();await expect(record.locator('pre').first()).toContainText(token);
 await page.screenshot({path:'../data/screenshots/approval-desktop.png',fullPage:true});
});
