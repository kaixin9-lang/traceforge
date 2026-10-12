import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:180000,workers:1,reporter:[['list'],['json',{outputFile:'../data/playwright-results.json'}]],use:{baseURL:'http://127.0.0.1:8000',trace:'retain-on-failure',screenshot:'only-on-failure'}});
