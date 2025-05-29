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
    --train_data ./data/dart/train.jsonl \
    --valid_data ./data/dart/valid.jsonl \
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
    --work_dir ./trained_models/GPT2_M/dart \
    --random_seed 2025

#推理测试
python src/gpt2_beam.py \
    --data ./data/dart/test.jsonl \
    --batch_size 1 \
    --seq_len 64 \
    --eval_len 32 \
    --model_card gpt2.sm \
    --init_checkpoint ./trained_models/GPT2_M/dart/model.1570.pkl \
    --lora_dim 4 \
    --lora_alpha 32 \
    --beam 10 \
    --length_penalty 0.8 \
    --no_repeat_ngram_size 4 \
    --repetition_penalty 1.0 \
    --eos_token_id 628 \
    --work_dir ./trained_models/GPT2_M/dart \
    --output_file predict.1570.b10p08r4.jsonl


##解码
python src/gpt2_decode.py \
    --vocab ./vocab \
    --sample_file ./trained_models/GPT2_M/dart/predict.1570.b10p08r4.jsonl \
    --input_file ./data/dart/test_formatted.jsonl \
    --ref_type dart \
    --ref_num 6 \
    --output_ref_file eval/GenerationEval/data/references_dart \
    --output_pred_file eval/GenerationEval/data/hypothesis_dart \
    --tokenize --lower

#计算指标

python eval/eval_m.py \
    -R eval/GenerationEval/data/references_dart/reference \
    -H eval/GenerationEval/data/hypothesis_dart \
    -nr 6 \
    -m bleu,meteor,ter \
    -who dart