import {test,expect} from '@playwright/test';
test('desktop pages, upload, live retrieval, diagnosis and persistence',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'从一段报错，找到问题的根源。'})).toBeVisible();
 await page.screenshot({path:'../data/screenshots/workbench-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'知识库',exact:true}).click();await expect(page.getByRole('heading',{name:'知识库',exact:true})).toBeVisible();
 const uploadName='e2e-trace-'+Date.now()+'.log';
 await page.locator('input[type=file]').setInputFiles({name:uploadName,mimeType:'text/plain',buffer:Buffer.from('FastAPI validation error: body.name field required. Request missing name property.')});
 await expect(page.getByRole('button',{name:uploadName})).toBeVisible({timeout:60000});
 await page.getByRole('button',{name:'检索实验',exact:true}).click();await page.getByLabel('检索问题').fill('FastAPI POST /items返回422，body.name缺少字段');await page.getByRole('button',{name:'运行检索'}).click();
 await expect(page.getByText('检索完成',{exact:true})).toBeVisible({timeout:90000});await expect(page.getByRole('heading',{name:'最终证据'})).toBeVisible();
 await page.screenshot({path:'../data/screenshots/retrieval-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'诊断工作台',exact:true}).click();await page.getByLabel('描述故障').fill('FastAPI POST /items返回422，detail.loc是body.name，应该如何排查？');await page.getByLabel('诊断模式').selectOption('knowledge');await page.getByRole('button',{name:'开始诊断'}).click();
 await expect(page.locator('.diagnosis-view .badge.completed')).toBeVisible({timeout:150000});await expect(page.locator('.diagnosis-view .markdown')).toContainText('422');
 await page.reload();await page.locator('.recent-list>button').first().click();await expect(page.locator('.diagnosis-view .markdown')).toContainText('422');
 await page.getByRole('button',{name:'评估中心',exact:true}).click();await expect(page.getByRole('heading',{name:'故障排查基准集'})).toBeVisible();
 await page.getByRole('button',{name:'项目与工具',exact:true}).click();await expect(page.getByRole('heading',{name:'MCP 连接'})).toBeVisible();
 await page.getByRole('button',{name:'系统设置',exact:true}).click();await expect(page.getByRole('heading',{name:'DeepSeek 大模型'})).toBeVisible();
 expect(errors).toEqual([]);
});
test('mobile navigation and layout',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.getByLabel('打开导航')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.screenshot({path:'../data/screenshots/workbench-mobile.png',fullPage:true});
 await page.getByLabel('打开导航').click();await page.getByRole('button',{name:'系统设置',exact:true}).click();await expect(page.getByRole('heading',{name:'系统设置'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
