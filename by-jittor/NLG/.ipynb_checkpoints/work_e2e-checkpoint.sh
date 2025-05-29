#计算资源不够，没办法
#export JT_SAVE_MEM=1
#export cpu_mem_limit=16000000000
#export device_mem_limit=7000000000
#
##查看异步报错
#export JT_SYNC=1
#export trace_py_var=3
#微调
python src/gpt2_ft.py \
    --train_data ./data/e2e/train.jsonl \
    --valid_data ./data/e2e/valid.jsonl \
    --train_batch_size 2 \
    --grad_acc 2 \
    --valid_batch_size 1 \
    --seq_len 64 \
    --model_card gpt2.sm \
    --init_checkpoint ./pretrained_checkpoints/gpt2-pytorch_model.bin \
    --clip 0.0 \
    --lr 0.0002 \
    --weight_decay 0.01 \
    --adam_beta2 0.999 \
    --scheduler linear \
    --warmup_step 500 \
    --max_epoch 5 \
    --save_interval 1000 \
    --lora_dim 4 \
    --lora_alpha 32 \
    --lora_dropout 0.1 \
    --label_smooth 0.1 \
    --work_dir ./trained_models/GPT2_M/e2e \
    --random_seed 2025

#推理测试
python src/gpt2_beam.py \
    --data ./data/e2e/test.jsonl \
    --batch_size 1 \
    --seq_len 64 \
    --eval_len 32 \
    --model_card gpt2.sm \
    --init_checkpoint ./trained_models/GPT2_M/e2e/model.1050.pkl \
    --lora_dim 4 \
    --lora_alpha 32 \
    --beam 10 \
    --length_penalty 0.8 \
    --no_repeat_ngram_size 4 \
    --repetition_penalty 1.0 \
    --eos_token_id 628 \
    --work_dir ./trained_models/GPT2_M/e2e \
    --output_file predict.1050.b10p08r4.jsonl


#解码
python src/gpt2_decode.py \
    --vocab ./vocab \
    --sample_file ./trained_models/GPT2_M/e2e/predict.1050.b10p08r4.jsonl \
    --input_file ./data/e2e/test_formatted.jsonl \
    --output_ref_file e2e_ref.txt \
    --output_pred_file e2e_pred.txt

#计算指标
python eval/e2e/measure_scores.py e2e_ref.txt e2e_pred.txt -p